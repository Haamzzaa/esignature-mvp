# Configuration Registry Documentation

This document describes all runtime configuration values managed by the centralized Configuration Registry (`esign/config.py`).

---

## Configuration Settings Registry

### 1. Security Settings

#### `FACE_MATCH_THRESHOLD`
* **Default Value**: `0.6` (Float)
* **Description**: Similarity threshold for biometric face comparison. Valid range: `0.0` (any match) to `1.0` (identical).
* **Override Mechanism**: Set `FACE_MATCH_THRESHOLD = 0.65` in Django settings.

#### `IDENTITY_MATCH_THRESHOLD`
* **Default Value**: `0.85` (Float)
* **Description**: String matching threshold for signatory candidate name matching (difflib score).
* **Override Mechanism**: Set `IDENTITY_MATCH_THRESHOLD = 0.9` in Django settings.

#### `ESIGN_OTP_EXPIRY_MINUTES`
* **Default Value**: `10` (Integer)
* **Description**: OTP expiration duration in minutes.
* **Override Mechanism**: Set `ESIGN_OTP_EXPIRY_MINUTES = 15` in Django settings.

#### `ESIGN_SIGNING_LINK_EXPIRY_HOURS`
* **Default Value**: `24` (Integer)
* **Description**: Link token validity period in hours.
* **Override Mechanism**: Set `ESIGN_SIGNING_LINK_EXPIRY_HOURS = 48` in Django settings.

#### `ESIGN_MAX_OTP_ATTEMPTS`
* **Default Value**: `5` (Integer)
* **Description**: Maximum allowable failed verification attempts.
* **Override Mechanism**: Set `ESIGN_MAX_OTP_ATTEMPTS = 3` in Django settings.

#### `ESIGN_MAX_UPLOAD_SIZE_BYTES`
* **Default Value**: `20971520` (Integer, 20 MB)
* **Description**: Maximum allowable contract analysis file upload limit.
* **Override Mechanism**: Set `ESIGN_MAX_UPLOAD_SIZE_BYTES = 52428800` (50 MB) in Django settings.

---

### 2. File Handling Settings

#### `ESIGN_ALLOWED_IMAGE_MIME_TYPES`
* **Default Value**: `['image/jpeg', 'image/jpg', 'image/png']` (List of Strings)
* **Description**: Accepted image MIME types for selfies and ID uploads.
* **Override Mechanism**: Set `ESIGN_ALLOWED_IMAGE_MIME_TYPES = ['image/jpeg', 'image/png']` in Django settings.

#### `ESIGN_ALLOWED_PDF_MIME_TYPES`
* **Default Value**: `['application/pdf']` (List of Strings)
* **Description**: Accepted document formats.
* **Override Mechanism**: Set `ESIGN_ALLOWED_PDF_MIME_TYPES = ['application/pdf']` in Django settings.

#### `ESIGN_MAX_PDF_SIZE_BYTES`
* **Default Value**: `10485760` (Integer, 10 MB)
* **Description**: Maximum PDF document size restriction.
* **Override Mechanism**: Set `ESIGN_MAX_PDF_SIZE_BYTES = 20971520` in Django settings.

#### `ESIGN_MAX_IMAGE_SIZE_BYTES`
* **Default Value**: `5242880` (Integer, 5 MB)
* **Description**: Maximum size restriction for identity/selfie image uploads.
* **Override Mechanism**: Set `ESIGN_MAX_IMAGE_SIZE_BYTES = 2097152` (2 MB) in Django settings.

---

### 3. OCR Settings

#### `ESIGN_OCR_PROVIDER`
* **Default Value**: `'paddle'` (String)
* **Description**: Active OCR library provider (e.g. `paddle`, `azure`).
* **Override Mechanism**: Set `ESIGN_OCR_PROVIDER = 'azure'` in Django settings.

#### `ESIGN_OCR_TIMEOUT_SECONDS`
* **Default Value**: `30` (Integer)
* **Description**: Timeout limit for network OCR API calls.
* **Override Mechanism**: Set `ESIGN_OCR_TIMEOUT_SECONDS = 15` in Django settings.

---

### 4. Face Verification Settings

#### `ESIGN_FACE_PROVIDER`
* **Default Value**: `'internal'` (String)
* **Description**: Underlying facial recognition implementation model.
* **Override Mechanism**: Set `ESIGN_FACE_PROVIDER = 'insightface'` in Django settings.

#### `ESIGN_LIVENESS_ENABLED`
* **Default Value**: `False` (Boolean)
* **Description**: Toggles whether signers must pass dynamic liveness analysis check.
* **Override Mechanism**: Set `ESIGN_LIVENESS_ENABLED = True` in Django settings.

---

### 5. Notification Settings

#### `ESIGN_REMINDER_INTERVAL_HOURS`
* **Default Value**: `24` (Integer)
* **Description**: Scheduled period between automated email reminders.
* **Override Mechanism**: Set `ESIGN_REMINDER_INTERVAL_HOURS = 48` in Django settings.

#### `ESIGN_NOTIFICATION_PROVIDER`
* **Default Value**: `'email'` (String)
* **Description**: Provider target for dispatches (`email`, `sms`, `pubsub`).
* **Override Mechanism**: Set `ESIGN_NOTIFICATION_PROVIDER = 'sms'` in Django settings.

---

### 6. General Settings

#### `ESIGN_API_VERSION`
* **Default Value**: `'v1'` (String)
* **Description**: Active version descriptor prefix for paths.
* **Override Mechanism**: Set `ESIGN_API_VERSION = 'v2'` in Django settings.

#### `ESIGN_MODULE_NAME`
* **Default Value**: `'esignature'` (String)
* **Description**: Internal module namespace identifier.
* **Override Mechanism**: Set `ESIGN_MODULE_NAME = 'esign'` in Django settings.
