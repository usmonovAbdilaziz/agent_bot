# Minimal taklif — 2026-11-03

Active entrypoint: main.py. Existing chat/relay code remains in legacy_bot.py and
legacy_webapp.py solely for regression and rollback; no legacy routes are mounted.
Existing database tables and records are preserved. New q_* tables store this flow.

Admin chooses self or a sender by international phone number. Only Telegram's own
contact (contact.user_id == from_user.id) verifies a phone. A bot cannot resolve an
arbitrary phone or initiate a chat with someone who has never started it. An invited
phone-selected sender therefore opens the ordinary bot link and shares their own
contact once. Self-registration requires the user's verified Telegram contact, then
a selection of 1, 10 or 30 links. The admin sees the phone and requested quantity.
Sender: optional photo / MP4 or video note <=60 seconds, <=20 MiB, or Skip;
default Telegram full name (editable); required description; preview; Confirm.
Confirm creates exactly one stable single-recipient link per draft, without moderation.
Receiver: /start i_TOKEN claims once and returns a single web_app button. Telegram
requires a user gesture to launch a Mini App. No API opens it automatically on /start.
Ha commits acceptance for that invitation and opens no chat. Historical q_done rows
do not block future deep links or sender requests. /start i_TOKEN always resolves
that token, even for a returning receiver or a user currently composing as sender.
An accepted/expired/claimed-by-another link cannot be reused; new links work.

Plain /start resumes an authorized draft or offers sender registration;
it does not silently reopen a previous receiver invitation. Confirmation creates one
pending request per user and notifies the configured admin with Approve/Reject.
Only that admin may decide; request IDs make stale decisions idempotent. Pending
requests and delivery state survive restart and appear in the admin request list.
Approval grants the requested number of sender credits. Publishing a draft consumes one in the
same transaction that creates the token. Retries reuse the token, never another grant.
Cancellation retains unspent credits; admin self-publishing remains unlimited.
Admin phone selection also grants at most one unspent permission; replaying a contact
does not replenish it. Legacy sender grants become one remaining permission, and
already-bound legacy phone grants are retired once during migration. Drafts/data stay.
Normal receiver text is ignored; ordinary /start remains available after acceptance.
Verified users may submit a text suggestion through /taklif. The admin reviews it;
approval atomically adds one credit, and repeat decisions cannot add it again. Request
and suggestion notices are persisted for retries. Decision notices report the outcome.

All /api routes require X-Telegram-Init-Data with validated Telegram HMAC and auth_date
between now-3600s and now+30s. All responses are no-store; tokens/file IDs are private.
GET /api/invites/{id}: sender preview or assigned receiver only; returns id, title,
description, media_kind (none/photo/video/video_note), status, preview; other users 404.
The response also contains design: classic, romantic, playful or elegant. Existing
invitations default to classic; legacy unknown designs are returned as classic. Sender selects it from the bot's draft preview.
The response also includes type (currently fun) and details (a JSON object). details.layout.text_position is top, center or bottom;
old records without it are returned with bottom. Invalid stored layouts cannot be published.
Publishing and design selection reject designs that do not belong to the invitation type.
GET /api/invites/{id}/media: same permission, bounded Telegram download proxied as
JPEG or MP4. No media =>404; upstream failure =>502. Browser uses authenticated fetch
and blob URL (no token-bearing remote URL). Video remains <=20 MiB for getFile.
New photos use the smallest Telegram variant with both dimensions at least 360 pixels,
or the largest available variant. Authorized photo downloads are cached in server memory
for up to 15 minutes (maximum 64 photos, 16 MiB total and 2 MiB per photo); responses
remain no-store and authorization is checked for every request. Existing photos retain
their stored variant; videos are not cached. Restart clears the cache.
POST /api/invites/{id}/accept: only assigned receiver; draft/expired =>409; sender =>403;
atomically transitions ready->accepted and records receiver completion. Repeats return
200 with accepted=true. Optional JSON body: {"no_attempts": 7}, integer 0..1000000;
missing body/field defaults to 0 for older clients. Invalid values/JSON =>400.
The first acceptance freezes this client-reported evasion count and atomically queues
one sender notification. Repeated accept requests cannot change it or queue another.
Notification states persist across restarts; temporary Telegram failures retry in the
background, blocked senders become failed. Acceptance remains successful on send errors.
Telegram sendMessage has no deduplication key: a crash/timeout after delivery but before
recording success can duplicate a notification. Normal repeat requests do not.
Browser remembers attempts per receiver/invite in localStorage when available. Each
existing evasion gesture counts once; preview does not count. No chat session opens.
GET /healthz: 200 only once bot startup is ready; otherwise 503.

Tailscale Funnel launcher supplies the HTTPS URL each run. Bot deep links remain
stable; reopening /start before acceptance generates a button with current tunnel URL.
Sources: https://core.telegram.org/bots/webapps ; https://core.telegram.org/bots/api#getfile
Orbit sendVideo discovery reviewed; official docs are authoritative for Mini App launch.
