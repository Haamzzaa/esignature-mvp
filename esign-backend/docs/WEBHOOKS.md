# Webhooks Documentation

This document describes the webhook dispatch architecture, payload formats, subscriber models, and failure recovery.

---

## 1. Webhook Subscription Model
Subscriptions are persisted in the database using the `WebhookSubscription` model.

* **Target URL**: Destination endpoint (HTTPS highly recommended).
* **Active Status**: Flag to enable/disable delivery.
* **Event Filter**: JSON list of subscribed topics (e.g. `["envelope.completed"]`) or `["*"]` to receive all notifications.

---

## 2. Dispatch Behavior
When a domain event occurs:
1. The event dispatcher publishes to `handle_webhooks`.
2. The webhook handler queries active subscriptions.
3. Matching subscribers receive an HTTP `POST` containing a JSON representation of the event payload.
4. Requests use the timeout value defined by `ESIGN_WEBHOOK_TIMEOUT_SECONDS` to prevent hangs.

---

## 3. Payload Format
Every webhook post uses the following standard payload format:

```json
{
  "event": "envelope.completed",
  "timestamp": "2026-06-27T07:45:20.123456Z",
  "data": {
    "envelope_id": 12,
    "base_api_url": "http://localhost:8000"
  }
}
```

---

## 4. Failure Handling and Future Roadmap
* **Timeouts**: Default delivery timeout is **10 seconds** (configurable).
* **Fail-Safe Processing**: Webhook delivery failures are logged under standard logger categories and isolated using sandbox blocks so they never interrupt critical business flows.
* **Future Retry Strategy**: In future versions, failed posts will be pushed to a database queue (e.g. Celery Task Queue) and retried with exponential backoff.
