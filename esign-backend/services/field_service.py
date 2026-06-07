from rest_framework.exceptions import ValidationError

def validate_field(field_data, participant_emails):
    """
    Validates field_data dictionary.
    participant_emails is a set of valid participant emails in the current envelope.
    """
    field_type = field_data.get('field_type')
    page = field_data.get('page')
    participant_email = field_data.get('participant_email')
    
    # 1. Check required fields
    if not field_type:
        raise ValidationError("Field type is required.")
    if page is None:
        raise ValidationError("Page number is required.")
    if not participant_email:
        raise ValidationError("Participant is required.")
        
    # 2. Check value constraints
    valid_types = ['signature', 'date', 'text', 'checkbox']
    if field_type not in valid_types:
        raise ValidationError(f"Invalid field type '{field_type}'. Supported types: {', '.join(valid_types)}.")
        
    try:
        page_val = int(page)
        if page_val < 1:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Page must be a positive integer.")
        
    if participant_email not in participant_emails:
        raise ValidationError(f"Participant email '{participant_email}' is not valid for this envelope.")

    x_ratio = field_data.get('x_ratio')
    y_ratio = field_data.get('y_ratio')
    if x_ratio is None or y_ratio is None:
        raise ValidationError("Field coordinates are required.")
    try:
        x = float(x_ratio)
        y = float(y_ratio)
        if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Coordinates must be float ratios between 0.0 and 1.0.")


def create_field(envelope, participant, field_type, page, x_ratio, y_ratio, required=True):
    """
    Creates and saves a DocumentField record.
    """
    from esign.models import DocumentField
    
    # Extra safety check
    valid_types = ['signature', 'date', 'text', 'checkbox']
    if field_type not in valid_types:
        raise ValidationError(f"Invalid field type '{field_type}'.")
        
    return DocumentField.objects.create(
        envelope=envelope,
        participant=participant,
        field_type=field_type,
        page=page,
        x_ratio=x_ratio,
        y_ratio=y_ratio,
        required=required
    )

def get_fields_for_participant(participant):
    """
    Queries all fields assigned to a specific participant.
    """
    from esign.models import DocumentField
    return DocumentField.objects.filter(participant=participant)
