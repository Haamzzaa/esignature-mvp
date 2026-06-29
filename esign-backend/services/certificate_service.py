import logging
import hashlib
import uuid
from django.utils import timezone
from django.core.files.base import ContentFile
from esign.models import CompletionCertificate, AuditLog
from services.pdf_service import generate_certificate_pdf

logger = logging.getLogger(__name__)

def generate_certificate(envelope):
    """
    Orchestrates the metadata collection and generates the PDF certificate of completion.
    Saves the generated file as a CompletionCertificate model linked to the envelope.
    """
    # Generate the unique Certificate ID once
    timestamp_str = timezone.now().strftime('%Y%m%d')
    cert_uuid = str(uuid.uuid4())[:8].upper()
    certificate_id = f"CERT-{timestamp_str}-{cert_uuid}"

    # 1. Fetch document hashes
    signed_doc = getattr(envelope, 'signeddocument', None)
    signed_hash = signed_doc.final_hash if signed_doc else "Unknown"
    
    # 2. Gather Timeline (AuditLog)
    audit_logs = AuditLog.objects.filter(envelope=envelope).order_by('timestamp')
    timeline = []
    for log in audit_logs:
        timeline.append({
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'event': log.event,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent,
        })
        
    # 3. Gather Participant details
    participants = []
    for p in envelope.participants.all().order_by('step_number', 'order', 'id'):
        # Find completion audit log to retrieve IP/UA evidence
        # Order by timestamp desc to get the latest action log
        p_log = audit_logs.filter(
            event__icontains=p.name
        ).order_by('-timestamp').first()
        
        # If no specific name-based event, fallback to generic completion log
        if not p_log:
            p_log = audit_logs.filter(
                event__icontains="Completed"
            ).order_by('-timestamp').first()
            
        participants.append({
            'name': p.name,
            'email': p.email,
            'role': p.get_role_display(),
            'completed_at': p.completed_at.strftime('%Y-%m-%d %H:%M:%S') if p.completed_at else "Pending",
            'ip_address': p_log.ip_address if p_log else None,
            'user_agent': p_log.user_agent if p_log else None,
        })
        
    # 4. Fallback for legacy workflow without participants (e.g. only legacy Signer is configured)
    if not participants:
        signer = getattr(envelope, 'signer', None)
        if signer:
            completed_log = audit_logs.filter(event__icontains="Completed").first() or audit_logs.filter(event="signed").first()
            participants.append({
                'name': signer.name,
                'email': signer.email,
                'role': 'Signer',
                'completed_at': envelope.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'ip_address': completed_log.ip_address if completed_log else None,
                'user_agent': completed_log.user_agent if completed_log else None,
            })
            
    # 5. Pack data dict
    data = {
        'package_id': envelope.id,
        'package_title': envelope.title or (envelope.document.file.name.rsplit('/', 1)[-1] if envelope.document and envelope.document.file else f"Package #{envelope.id}"),
        'completion_date': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'owner_email': envelope.owner.email if envelope.owner else "Unknown",
        'document_hash': signed_hash,
        'participants': participants,
        'timeline': timeline,
        'generation_timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'certificate_id': certificate_id,
    }
    
    # 6. Render PDF bytes
    pdf_bytes = generate_certificate_pdf(data)
    
    # Calculate SHA256 of the generated certificate itself
    cert_hash = hashlib.sha256(pdf_bytes).hexdigest()
    
    # 7. Persist Certificate to Database
    # Delete any existing certificate for this envelope first to allow regeneration / clean state
    CompletionCertificate.objects.filter(envelope=envelope).delete()
    
    cert_filename = f"certificate_package_{envelope.id}.pdf"
    
    cert_obj = CompletionCertificate(envelope=envelope, certificate_id=certificate_id, final_hash=cert_hash)
    cert_obj.file.save(cert_filename, ContentFile(pdf_bytes), save=True)
    
    # Log audit event for certificate generation
    AuditLog.objects.create(
        envelope=envelope,
        event=f"Certificate of Completion Generated: {certificate_id}",
    )
    
    return cert_obj
