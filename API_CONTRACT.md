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
With ENABLE_CEREMONY=true, sender selects fun or ceremony; default false goes directly to fun. Fun: optional photo / MP4 or video note <=60 seconds, <=20 MiB, or Skip;
default Telegram full name (editable); required description; preview; Confirm.
Confirm creates one stable link per draft; fun and personal ceremony bind one receiver, open ceremony supports multiple guests.
Receiver: /start i_TOKEN returns a web_app button; a single link binds one receiver, while each open-link visitor is authorized separately. Telegram
requires a user gesture to launch a Mini App. No API opens it automatically on /start.
Ha commits acceptance for that invitation and opens no chat. Historical q_done rows
do not block future deep links or sender requests. /start i_TOKEN always resolves
that token, even for a returning receiver or a user currently composing as sender.
Fun/single links cannot be claimed by another receiver; previously answered ceremony guests retain access after expiry.

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
GET /api/invites/{id}: sender preview, assigned receiver or authorized open-link visitor; returns id, title,
description, media_kind (none/photo/video/video_note), status, preview; other users 404.
The response also contains a registry-backed design. Existing
invitations default to classic; legacy unknown designs are returned as classic. Sender selects it from the bot's draft preview.
The response also includes type (fun or ceremony) and details (a JSON object). details.layout.text_position is top, center or bottom;
old records without it are returned with bottom. Invalid stored layouts cannot be published.
Publishing and design selection reject designs that do not belong to the invitation type.
Ceremony details require event_kind (wedding, nikah, beshik, sunnat, fotiha, birthday, other), date (DD.MM.YYYY, not before the current Asia/Tashkent date at publish), time (HH:MM), address (1–300 characters), map_url (empty or an allowlisted HTTPS map URL, at most 500 characters), program (up to 20 nonempty lines, 200 characters each and 800 in total), note (1–500 characters), and layout. Title is 1–120 characters. Draft updates validate each supplied field and publication validates the complete schema. User text is stored verbatim and escaped for Telegram HTML output. Single mode binds one receiver; open mode is available to each user who opened the token link.
GET additionally returns rsvp: null or {attending: 0|1, guests: 0..10, responded_at: Unix seconds}. POST /api/invites/{id}/rsvp requires an authenticated authorized receiver of a ready ceremony invitation, including each open-link visitor and JSON {attending: 0|1, guests: integer}. Attending guests are 1..10; declining permits 0 or 1 and stores 0. Success returns 200 {rsvp: {attending, guests, responded_at}}. Invalid JSON/values =>400, unauthorized =>401/403/404, non-ceremony or expired =>409. The first answer and its notification state are stored atomically: the first 50 are pending, later notices suppressed; repeated valid submissions return the original answer unchanged. Sender notifications retry after temporary failures; ambiguous Telegram timeouts can result in duplicate notifications.
GET /api/invites/{id}/media: same permission, bounded Telegram download proxied as
JPEG or MP4. No media =>404; upstream failure =>502. Browser uses authenticated fetch
and blob URL (no token-bearing remote URL). Video remains <=20 MiB for getFile.
New photos use the smallest Telegram variant with width at least 720 pixels,
or the largest available variant. Authorized photo and small video downloads are cached in server memory
for up to 15 minutes (maximum 64 photos, 16 MiB total and 2 MiB per photo); responses
remain no-store and authorization is checked for every request. Existing photos retain
their stored variant; files over 2 MiB are not cached. Restart clears the cache.
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

### M4b: ochiq havola va RSVP

`GET /api/invites/{id}` javobida `share_mode` (`single` yoki `open`) bor. Yangi ceremony uchun standart `open`, fun uchun `single`; eski takliflar `single` qoladi. Ochiq taklifni ko‘rish uchun foydalanuvchi avval botdagi tokenli havolani ochishi, barcha API so‘rovlarida esa haqiqiy Telegram `initData` yuborishi kerak. Sender preview javoblarni oshkor qilmaydi. `rsvp` faqat joriy foydalanuvchining javobi.

`POST /api/invites/{id}/rsvp` har bir `(invite_id, telegram_user_id)` uchun dastlabki javobni saqlaydi va keyingi so‘rovlarda o‘sha javobni qaytaradi. Chegaraga yetgan yangi javob 409; foydalanuvchining so‘rov tezligi oshsa 429 va tushunarli `error` qaytadi. Standart limit 500, tezlik 30 so‘rov/daqiqa; mos ravishda `RSVP_MAX_RESPONSES` va `RSVP_RATE_LIMIT_PER_MINUTE` bilan sozlanadi. Tezlik chegarasi jarayon xotirasida bo‘lib, qayta ishga tushganda tiklanadi. Dastlabki 50 ta RSVP uchun alohida sender xabari outbox orqali yuboriladi; keyingilari faqat `/guests` ro‘yxatida ko‘rinadi.

Ceremony `GET` javobidagi `rsvp_closed` marosim kuni Toshkent vaqtida tugagach `true` bo‘ladi. Shu vaqtdan so‘ng yangi RSVP 409 qaytaradi; avvalgi javob idempotent qaytariladi va egasiga ko‘rinishda qoladi.

Feature flag `ENABLE_CEREMONY` controls new bot creation only (default false). Existing ceremony links, RSVP and guest access remain available when off.

New ceremony links expire at midnight Asia/Tashkent following the event day plus 24 hours, capped at 400 days after publication. Fun retains configured TTL; existing stored expiry is unchanged. RSVP closes at event-day midnight, returning HTTP 409 with `code: rsvp_closed` for a new response. Authenticated media supports a single byte Range (206, or 416 for invalid/unsatisfiable range). Media downloads are single-flight per file with configurable global concurrency (default 4), per-user request rate (default 120/minute), shared in-memory 16 MiB/64-entry cache, 2 MiB item limit and 15-minute TTL; no media is written to disk.
