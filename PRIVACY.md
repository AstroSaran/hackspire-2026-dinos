# Kavach privacy notes

## What the app stores

Live weather and public-feed responses are fetched from providers and are not associated with a user account. AI conversations are not saved by default. A signed-in user can explicitly save selected chat answers or voice transcripts as notes. Short speech-to-text clips are sent to the configured transcription provider (ElevenLabs when configured, otherwise Gemini) and are not saved by Kavach. If a user chooses voice cloning, their audio samples are sent to ElevenLabs after the UI confirms speaker authorization and separate provider-sharing consent; Kavach holds the bytes in memory for the request and does not persist them. Generated speech text is sent to ElevenLabs when a voice is configured. Provider storage, retention, and use are subject to the provider's terms and account settings.

An account stores an email address, an Argon2 password hash, a token version, and timestamps. Notes store their type, title, tags, optional fields, source label, owner ID, and timestamps. The note body is encrypted with Fernet before it is written to MongoDB. Refresh token hashes are stored with a 30-day expiry; MongoDB TTL cleanup may run after the expiry instant.

## Where and how long

Data is stored in the MongoDB database configured through `MONGODB_URI` and `MONGODB_DB_NAME`. Development may use a local MongoDB. Production requires MongoDB access control, TLS and protected backups. The application hard-deletes notes on user deletion and hard-deletes the account and its notes when requested. Backups operated outside this application may retain prior copies according to the database operator's retention policy.

## User controls

Users can list, edit, export, and delete their own notes from Kavach. Deleting the account removes that account and its notes and revokes sessions. Signing out revokes current account tokens. The dashboard keeps the access token in memory and does not persist it in local storage.

Notes are labeled “Your note: not verified by Kavach”. Notes are never mixed into live-data panels or provider evidence snapshots. A future explicit “use my notes” action would require a clear per-question selection; this build does not send notes to Gemini.

## Review

This notice describes this implementation, not legal advice or a claim of legal compliance. Review data handling, retention, consent and applicable law before any public or production use.
