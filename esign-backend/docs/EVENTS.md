# Domain Events Documentation

This document describes the design, standard naming conventions, payload schemas, and lifecycle of Domain Events in the E-Signature platform.

---

## 1. Event Naming Standards
We follow a dot-separated, hierarchy-based naming structure in lowercase:
* `[resource].[action]`
* `[resource].[sub-resource].[action]`

Example naming conventions:
* `envelope.created`
* `envelope.sent`
* `envelope.completed`
* `participant.completed`
* `verification.otp.verified`
* `verification.face.completed`
* `manual_review.requested`

---

## 2. Event Lifecycle & Dispatch Flow

All domain events inherit from the abstract class `DomainEvent` ([base.py](file:///c:/Users/Mohammed%20Hamza/esign_Module/esign-backend/esign/events/base.py)). 

1. **Instantiation**: Business layers instantiate events (e.g. `EnvelopeSent`).
2. **Publishing**: Services invoke `esign_dispatcher.publish(event)` ([dispatcher.py](file:///c:/Users/Mohammed%20Hamza/esign_Module/esign-backend/esign/events/dispatcher.py)).
3. **Execution**: The dispatcher iterates through registered callback handlers synchronously in try-catch sandboxes, isolating failures.

---

## 3. Supported Events & Payload Structure

### `envelope.sent`
* **Triggered When**: The envelope is sent to its first signer.
* **Payload**:
  ```json
  {
    "envelope_id": 12,
    "expires_at": "2026-06-28T07:12:16Z",
    "base_api_url": "http://localhost:8000"
  }
  ```

### `envelope.completed`
* **Triggered When**: The final participant signs, and the envelope is fully executed.
* **Payload**:
  ```json
  {
    "envelope_id": 12,
    "base_api_url": "http://localhost:8000"
  }
  ```

### `participant.completed`
* **Triggered When**: A single signer finishes their step in the workflow.
* **Payload**:
  ```json
  {
    "participant_id": 34,
    "envelope_id": 12,
    "role": "signer",
    "step_number": 2,
    "base_api_url": "http://localhost:8000"
  }
  ```
