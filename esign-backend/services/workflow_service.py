import logging
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from esign.models import Envelope, ParticipantToken, Signer, SigningToken, AuditLog

logger = logging.getLogger(__name__)

def activate_workflow_step(envelope, step_number):
    """
    Activates all participants in the specified step_number for the envelope,
    generating/regenerating their ParticipantToken.
    Also updates legacy Signer/SigningToken dynamically if a signer participant is activated.
    """
    # Transition all participants in this step to active
    step_participants = envelope.participants.filter(step_number=step_number)
    for p in step_participants:
        p.status = 'active'
        p.save(update_fields=['status'])
        
        # Spawn unique ParticipantToken
        ParticipantToken.objects.filter(participant=p).delete()
        ParticipantToken.objects.create(
            participant=p,
            expires_at=timezone.now() + timedelta(hours=24),
            is_used=False
        )
        
        # Keep legacy Signer/SigningToken synced for compatibility
        if p.role == 'signer':
            signer_rec = Signer.objects.filter(envelope=envelope).first()
            if signer_rec:
                signer_rec.name = p.name
                signer_rec.email = p.email
                signer_rec.save()
                
                # Provision signing token
                SigningToken.objects.filter(signer=signer_rec).delete()
                SigningToken.objects.create(
                    signer=signer_rec,
                    expires_at=timezone.now() + timedelta(hours=24),
                    is_used=False
                )


@transaction.atomic
def check_and_advance_step(envelope, current_step, request=None):
    """
    Checks if all participants in current_step have completed their actions.
    If so, transitions step, activates the next step participants, and advances the workflow.
    """
    ip_address = request.META.get("REMOTE_ADDR") if request else None
    user_agent = request.META.get("HTTP_USER_AGENT") if request else None

    # Acquire row-level locks - trust caller to own them to keep lock scope minimal
    step_participants = envelope.participants.filter(step_number=current_step)
    
    all_step_completed = True
    for p in step_participants:
        if p.status != 'completed':
            all_step_completed = False
            break

    if all_step_completed:
        # Check if Step Completed audit has already been logged to avoid double entries
        completed_event = f"Step {current_step} Completed"
        AuditLog.objects.get_or_create(
            envelope=envelope,
            event=completed_event,
            defaults={
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )

        # Check for next step in sequential routing
        next_participants = envelope.participants.filter(step_number__gt=current_step).order_by('step_number')
        if next_participants.exists():
            next_step = next_participants.first().step_number
            
            # Activate next step participants
            activate_workflow_step(envelope, next_step)
            
            AuditLog.objects.create(
                envelope=envelope,
                event="Workflow Advanced",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event=f"Step {next_step} Activated",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            # Keep/reset envelope status to sent so the next participants can perform actions
            envelope.transition_to("sent")

            # Send next step email notifications post-commit.
            # A failure here must NOT unwind the workflow advance already committed above.
            from services.notification_service import send_next_step_notifications
            
            def _notify_next_step():
                try:
                    send_next_step_notifications(envelope, next_step, request)
                except Exception:
                    logger.exception(
                        "Failed to send step %s notification email for envelope %s",
                        next_step,
                        envelope.id,
                    )
            transaction.on_commit(_notify_next_step)
        else:
            # Final workflow step completed! Mark envelope as completed
            envelope.transition_to("completed")

            # Create completion audit logs first so that they appear on the certificate timeline
            AuditLog.objects.create(
                envelope=envelope,
                event="Workflow Completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="Signed Document Generated",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            AuditLog.objects.create(
                envelope=envelope,
                event="Document Available",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            # Legacy "completed" audit event
            AuditLog.objects.create(
                envelope=envelope,
                event="completed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Schedule post-commit side effects.
            # Both generate_certificate() and send_completion_email() run AFTER the
            # atomic block commits. A failure in either cannot roll back the completed
            # envelope status or any of the audit logs saved above.
            def _post_commit_side_effects():
                from services.certificate_service import generate_certificate
                from services.notification_service import send_completion_email
                cert_id = None
                try:
                    logger.info(
                        "Generating completion certificate for envelope %s", envelope.id
                    )
                    cert_obj = generate_certificate(envelope)
                    cert_id = cert_obj.certificate_id
                except Exception:
                    logger.exception(
                        "Failed to generate certificate for envelope %s", envelope.id
                    )
                try:
                    send_completion_email(envelope, cert_id, request)
                except Exception:
                    logger.exception(
                        "Failed to send completion email for envelope %s", envelope.id
                    )

            transaction.on_commit(_post_commit_side_effects)
