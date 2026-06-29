from esign.events.base import DomainEvent

class EnvelopeCreated(DomainEvent):
    def __init__(self, envelope_id: int, title: str, status: str, owner_id: int | None):
        super().__init__("envelope.created", {
            "envelope_id": envelope_id,
            "title": title,
            "status": status,
            "owner_id": owner_id,
        })

class EnvelopeSent(DomainEvent):
    def __init__(self, envelope_id: int, expires_at: str):
        super().__init__("envelope.sent", {
            "envelope_id": envelope_id,
            "expires_at": expires_at,
        })

class EnvelopeViewed(DomainEvent):
    def __init__(self, envelope_id: int, ip_address: str = None):
        super().__init__("envelope.viewed", {
            "envelope_id": envelope_id,
            "ip_address": ip_address,
        })

class EnvelopeCompleted(DomainEvent):
    def __init__(self, envelope_id: int):
        super().__init__("envelope.completed", {
            "envelope_id": envelope_id,
        })

class EnvelopeDeclined(DomainEvent):
    def __init__(self, envelope_id: int, reason: str = ""):
        super().__init__("envelope.declined", {
            "envelope_id": envelope_id,
            "reason": reason,
        })

class EnvelopeCancelled(DomainEvent):
    def __init__(self, envelope_id: int):
        super().__init__("envelope.cancelled", {
            "envelope_id": envelope_id,
        })

class ParticipantCompleted(DomainEvent):
    def __init__(self, participant_id: int, envelope_id: int, role: str):
        super().__init__("participant.completed", {
            "participant_id": participant_id,
            "envelope_id": envelope_id,
            "role": role,
        })

class ParticipantDeclined(DomainEvent):
    def __init__(self, participant_id: int, envelope_id: int, reason: str = ""):
        super().__init__("participant.declined", {
            "participant_id": participant_id,
            "envelope_id": envelope_id,
            "reason": reason,
        })

class OTPVerified(DomainEvent):
    def __init__(self, participant_id: int, otp_type: str):
        super().__init__("verification.otp.verified", {
            "participant_id": participant_id,
            "otp_type": otp_type,
        })

class IdentityVerified(DomainEvent):
    def __init__(self, participant_id: int, matched: bool, score: float):
        super().__init__("verification.identity.verified", {
            "participant_id": participant_id,
            "matched": matched,
            "score": score,
        })

class FaceVerified(DomainEvent):
    def __init__(self, participant_id: int, matched: bool, score: float):
        super().__init__("verification.face.completed", {
            "participant_id": participant_id,
            "matched": matched,
            "score": score,
        })

class ManualReviewRequested(DomainEvent):
    def __init__(self, participant_id: int, reason: str):
        super().__init__("manual_review.requested", {
            "participant_id": participant_id,
            "reason": reason,
        })

class ManualReviewApproved(DomainEvent):
    def __init__(self, participant_id: int):
        super().__init__("manual_review.approved", {
            "participant_id": participant_id,
        })

class ManualReviewRejected(DomainEvent):
    def __init__(self, participant_id: int, reason: str):
        super().__init__("manual_review.rejected", {
            "participant_id": participant_id,
            "reason": reason,
        })
