from esign.events.dispatcher import esign_dispatcher
from esign.events.handlers import (
    handle_envelope_sent,
    handle_envelope_completed,
    handle_next_workflow_step,
    handle_audit_logging,
    handle_webhooks,
)

def register_built_in_handlers():
    """
    Registers the E-Signature module built-in handlers to the dispatcher registry.
    """
    # 1. Envelope events
    esign_dispatcher.register("envelope.sent", handle_envelope_sent)
    esign_dispatcher.register("envelope.sent", handle_webhooks)
    
    esign_dispatcher.register("envelope.completed", handle_envelope_completed)
    esign_dispatcher.register("envelope.completed", handle_webhooks)
    
    esign_dispatcher.register("envelope.viewed", handle_audit_logging)
    esign_dispatcher.register("envelope.viewed", handle_webhooks)
    
    esign_dispatcher.register("envelope.created", handle_webhooks)
    esign_dispatcher.register("envelope.declined", handle_webhooks)
    esign_dispatcher.register("envelope.cancelled", handle_webhooks)

    # 2. Participant events
    esign_dispatcher.register("participant.completed", handle_next_workflow_step)
    esign_dispatcher.register("participant.completed", handle_webhooks)
    
    esign_dispatcher.register("participant.declined", handle_webhooks)

    # 3. Verification events
    esign_dispatcher.register("verification.otp.verified", handle_webhooks)
    esign_dispatcher.register("verification.identity.verified", handle_webhooks)
    esign_dispatcher.register("verification.face.completed", handle_webhooks)

    # 4. Manual review events
    esign_dispatcher.register("manual_review.requested", handle_webhooks)
    esign_dispatcher.register("manual_review.approved", handle_webhooks)
    esign_dispatcher.register("manual_review.rejected", handle_webhooks)
