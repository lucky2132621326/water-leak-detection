# Twilio WhatsApp Leak Alerts

The backend queues one WhatsApp Content Template message when a new confirmed
leak incident is created. Later telemetry samples merge into that incident and
do not send duplicates. Delivery runs in a background worker; Twilio errors are
logged and never stop telemetry ingestion or leak detection.

## Security first

Never paste or commit an auth token. If a token appears in chat, a screenshot,
or Git history, rotate it immediately in the Twilio Console. The application
reads credentials from environment variables and `.env` is ignored by Git.

## Setup

1. Copy `.env.example` to `.env`.
2. Configure the Twilio WhatsApp Sandbox or an approved WhatsApp sender.
   Sandbox recipients must join the sandbox before Twilio can message them.
3. Create and approve a `twilio/text` Content Template with this exact body:

```text
🚨 LEAK DETECTED
Location: {{1}}
Estimated leak rate: {{2}} L/min
Confidence: {{3}} ({{4}}%)
Detected: {{5}}
Action: {{6}}
```

The variables are zone, leak rate, confidence tier, likelihood percentage,
event time in IST, and operator action respectively. Copy the approved `HX...`
SID into `.env`.
4. Put the rotated account SID/token, sender, recipient, and Content SID in `.env`.
5. Set `TWILIO_WHATSAPP_ENABLED=true` and restart the Python API.

```dotenv
TWILIO_WHATSAPP_ENABLED="true"
TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_AUTH_TOKEN="replace-with-rotated-token"
TWILIO_WHATSAPP_FROM="whatsapp:+14155238886"
TWILIO_WHATSAPP_TO="whatsapp:+91XXXXXXXXXX"
TWILIO_CONTENT_SID="HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_ALERT_ACTION="Inspect the pipeline and verify in the field."
TWILIO_NOTIFY_MOCK="false"
```

Mock notifications are disabled by default because synthetic scenarios can loop.
Set `TWILIO_NOTIFY_MOCK=true` only for a deliberate notification demo.
Deduplication is process-local; a durable outbox is the next step if guaranteed
delivery across restarts is required.

The Twilio form contains `From`, `To`, `ContentSid`, and `ContentVariables` as
six values matching the contract above. Tests mock the transport and never
contact Twilio. WhatsApp must approve the template before business-initiated
messages can use it.

```bash
python -m pytest tests/test_whatsapp_notifier.py
```
