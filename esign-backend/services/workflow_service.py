import logging
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from esign.models import ParticipantToken, Signer, SigningToken, AuditLog

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

    step_participants = envelope.participants.filter(step_number=current_step)
    
    all_step_completed = True
    for p in step_participants:
        if p.status != 'completed':
            all_step_completed = False
            break

    if all_step_completed:
        # Check if Step Completed audit has already been logged to avoid double entries
        completed_event = f"Step {current_step} Completed"
        if not AuditLog.objects.filter(envelope=envelope, event=completed_event).exists():
            AuditLog.objects.create(
                envelope=envelope,
                event=completed_event,
                ip_address=ip_address,
                user_agent=user_agent,
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
            envelope.status = "sent"
            envelope.save(update_fields=["status"])

            # Send next step email notifications
            from services.notification_service import send_next_step_notifications
            send_next_step_notifications(envelope, next_step, request)
        else:
            # Final workflow step completed! Mark envelope as completed
            envelope.status = "completed"
            envelope.save(update_fields=["status"])

            # Send completion email to owner and additional recipients
            from services.notification_service import send_completion_email
            send_completion_email(envelope, request)

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
