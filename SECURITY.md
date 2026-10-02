# Kavach key handling

`backend/.env` is private and is ignored by Git. Do not include it in a ZIP, screenshot, issue, or shared folder. Never put provider keys in dashboard HTML/JavaScript. The `.env.example` file contains placeholders only.

The Gemini key previously pasted in the project conversation should be rotated manually in Google AI Studio: revoke the exposed key, create a replacement, update `backend/.env`, restart Kavach, and verify `/support/status`. Do not send the replacement key in chat.

For a public deployment, use a secret manager, HTTPS, access controls, and a restrictive `KAVACH_ALLOWED_ORIGINS` list. Local development should bind to `127.0.0.1`.
