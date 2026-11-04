# Minimal taklif — tekshiruv hisoboti

Sana: 2026-11-03. **Yangi minimal bot jonli ishga tushirildi.**

## Jonli ishga tushirish — 10:05 (Asia/Tashkent)

Foydalanuvchi ngrok tokenini kiritib, qayta ishga tushirishga ruxsat berdi.
Eski bot to‘xtatildi; SQLite oldindan backup qilindi. 8080-port boshqa Java dasturiga
tegishli bo‘lgani uchun lokal WEBAPP_PORT=8081 qilindi. Java jarayoniga tegilmadi.
Ngrok web_addr=:0 bilan pyngrok readiness cho‘zilishi aniq lokal boshqaruv porti
ajratish orqali tuzatildi. Ngrok ogohlantirishlarida tokenlar yashiriladi.

Jonli dalillar: lokal /healthz=200; tashqi HTTPS /healthz=200; yangi index va
JavaScript=200; autentifikatsiyasiz API=401. Telegram getMe: @Qadam_n1_bot;
getMyCommands: faqat start; menu: commands. Bitta bot, bitta launcher va ngrok ishlaydi.
Launcher tuzatishlaridan keyin 7 test o‘tdi (0.14s).
Haqiqiy receiver bilan tugmalar/MP4/yopilishning oxirigacha sinovi hali alohida.
Token va foydalanuvchi ma’lumotlarisiz texnik dalil: `.runtime/live-evidence.json`.

Quyidagi lokal testlar va ishga tushirishdan oldingi holat tarix sifatida saqlandi.

## Natija

- Postman Telegram HTTP simulyatori bilan to‘liq suite: **64 passed in 25.28s**.
- Yakuniy acceptance-lock va yuborilmagan havolani /start orqali tiklash tuzatishidan
  keyin yangi oqim: **14 passed in 5.17s**.
- Playwright Chromium: **280×600, 390×844, 1280×800** ko‘rinishlar o‘tdi.
- Video UI: browserda kodlangan VP8 test fayli dekodlandi, dumaloq video va ovoz
  yoqish/o‘chirish ishladi. Bu haqiqiy Telegram MP4 yetkazilishi sinovi emas.
- Python compile va JavaScript syntax tekshirildi.
- Impeccable detector hech qanday finding bermadi; HTMLdagi absolut stylesheet
  yo‘lini o‘zi yecholmagani haqida cheklov chiqardi. CSS alohida kiritildi va real
  browser screenshotlari ko‘zdan kechirildi.

## Tekshirilgan xatti-harakatlar

Admin: faqat O‘zim / Boshqa raqam; begona odam admin amallarini bajara olmaydi.
Sender raqami: faqat contact.user_id yuboruvchining o‘ziga teng bo‘lsa tasdiqlanadi;
admin tanlamagan raqam sender huquqini olmaydi. Oldin tasdiqlangan raqam tanlanishi ham
tekshirildi. Telefon HMAC ko‘rinishida saqlanadi.

Sender oqimi: mediasiz davom etish, photo, video va video_note, 60/61 sekund chegarasi,
20 MiB chegarasi, full name default, ism/tavsif uzunligi, tahrirlash, preview,
restartdan davom etish. Stale callbacklar va takror kelgan message IDlar bosqichni
siljitmaydi. Confirm bir token beradi, takror tasdiqlash link xabarini ko‘paytirmaydi.
Telegram xato javobi bo‘lsa tayyor havola /start orqali tiklanadi.

Receiver: first claim atomik, egasi o‘z havolasini sarflamaydi, ikkinchi hisob kira
olmaydi. /start bitta web_app tugmasini beradi. Ha idempotent, q_done atomik yoziladi,
relay sessiyasi ochilmaydi. Keyingi /start va xabarlar, shu jumladan restartdan keyin,
Telegramga hech qanday javob so‘rovini yaratmaydi.

HTTP: initData imzosi, muddati, boshqa foydalanuvchiga 404, sender acceptiga 403,
expired taklifga 409, rasmning faqat egasi/receiverga ochilishi, yo‘q mediaga 404,
faol bo‘lmagan eski API marshrutlari va readiness tekshirildi.

UI: 10 keyboard urinishdan keyin stiker, 11-urinishda yana harakat, touch event,
Ha bilan ustma-ust kelmaslik, horizontal overflow yo‘qligi, failed accept → retry,
server muvaffaqiyatidan keyin rahmat/fireworks va close() chaqirig‘i, sender previewda
Ha/Yo‘q o‘chirilganligi. Preview screenshotidagi M namunaviy test rasmi.

## Dalillar

- `output/minimal/browser-results.json`
- `output/minimal/mobile-no-media.png`
- `output/minimal/mobile-preview.png`
- `output/minimal/mobile-video.png`
- `output/minimal/mobile-sticker.png`
- `output/minimal/desktop-accepted.png`
- Postman simulyatori 4629 portda ishlatildi; main startup/polling hamda yangi video
  yaratish oqimida Bot API chaqiriqlari mock orqali o‘tdi.

## Ishga tushirishdan oldingi muhit (yuqorida hal qilingan)

Postman CLI o‘rnatilgan, simulation ishlaydi. Ushbu versiyada `postman status`
qo‘llanmaydi; workspace discovery/publish bajarilmadi. Orbit sendVideo briefi va
Telegram rasmiy Mini App/getFile hujjatlari ishlatildi.

`.env`da BOT_TOKEN va ADMIN_PHONE mavjud, **NGROK_AUTHTOKEN mavjud emas**.
Eski bot jarayoni ishlamoqda; yangi main.py ni jonli qayta ishga tushirish bajarilmadi.
Avval tokenni `.env`ga qo‘shish va qayta ishga tushirishga ruxsat kerak.
Telegram kanalida designated responder yo‘qligi sabab savol lokal yuborildi.

Jonli qabul sinovi: admin /start → sender tanlash → haqiqiy rasm/MP4 yoki mediasiz
variant → preview → tasdiqlash → boshqa hisobda havola → Taklifni ochish → 10 marta
Yo‘q → Ha → Telegram oynasi yopilishi → receiver /startga javob yo‘qligi.
Mahalliy UI close() chaqirig‘ini tekshiradi; haqiqiy Telegram klientining yopilishini
isbotlamaydi. Bu farq jonli sinovda tasdiqlanishi kerak.

Eski ma’lumotlar o‘chirilmagan. Manba backupi:
`backups/source-before-minimal-20261103.zip`. Bu manba backupi, jonli baza nusxasi emas.

Yangi statik sahifa `web_minimal/`ga ajratildi. Eski jarayon hali `web/`ni
ishlatgani sabab u papka manba backupidan aynan tiklandi; jonli eski frontend
va yangi API bir-biriga aralashmaydi. Yangi main faqat web_minimal sahifasini beradi.

Statik papka ajratilgach joriy main startup va minimal video Postman sinovlari
qayta bajarildi; haqiqiy lokal HTTP server yangi index va JavaScriptni beradi.
# Windows one-click package — 2026-11-03

start.bat now invokes the bundled Windows PowerShell launcher. It locates a
64-bit Python 3.11–3.13 interpreter, or downloads the official Python 3.13.17
Windows x64 installer, verifies its published SHA256, and installs per-user.
The installer uses no system PATH changes. A named mutex prevents duplicate
launches from the same folder while dependencies are being installed.

run.py preserves a broken/copied virtual environment under a backup name before
recreating it, restores missing pip through ensurepip, and repairs missing modules.
setup_config.py prompts once for missing/invalid BOT_TOKEN, ADMIN_PHONE and
NGROK_AUTHTOKEN, preserves existing settings, and keeps secret input hidden.
Windows launcher child uses a new process group so Ctrl+C can request cleanup via
CTRL_BREAK_EVENT; an owned process-tree kill is the final timeout fallback.

Validation: **102 passed, 5 skipped in 41.07s** on macOS. The five Postman tests
require the separate HTTP simulation and were not needed for this packaging change.
Tests include real temporary venv creation, missing pip restoration without network,
configuration persistence and retry validation, plus modeled Windows shutdown paths.
pip dry-run with --platform win_amd64 --python-version 3.13 --only-binary=:all:
resolved every requirements.txt dependency successfully, including native wheels.
Windows scripts are packaged with CRLF. ZIP excludes .env, databases and .runtime.

No Windows host, Wine or PowerShell runtime was available here. Actual double-click,
installer execution, Windows process signals and live Telegram/ngrok on Windows
have NOT been verified. Existing live Mac bot was not restarted or stopped.

Installer checksum/source: https://www.python.org/downloads/release/python-31317/
Installer options: https://docs.python.org/3.13/using/windows.html
Python 3.13.17 is the final 3.13 Windows installer; 3.13.18 is source-only.

# Per-invitation receiver state and one-link sender approval — 2026-11-03

Replaced the global receiver mute with per-invitation completion. Fresh deep links
work for returning users, including previously accepted receivers and active senders.
Plain /start offers sender confirmation or resumes an authorized draft; it does not
reopen an old receiver invitation. Request IDs and a pending-request unique index
deduplicate consent/decisions. Only the configured admin can approve or reject.

Approval or phone assignment grants one unspent permission, consumed atomically
on publication. Draft cancellation retains permission. Repeated contact, old admin
decisions and old creation buttons cannot replenish it. Existing sender grants now
mean one remaining permission; migration retires bound legacy permanent phone grants
while preserving outstanding unbound phone assignments, drafts and invitation data.
Admin self-publication is exempt. Failed link delivery remains recoverable after
permission consumption. Request/admin decision delivery state survives restarts.

Validation: **97 passed in 39.40s** with local Postman simulation on port 4629.
Includes 12 focused sender/session tests, HTTP permission tests, prior notification,
launcher and legacy regressions. Actual mock log recorded 69 sendMessage calls;
HTTP statuses across requests: 133 successful, 2 explicit 403, 3 explicit 500.
The simulated Dispatcher flow covers a returning receiver requesting approval,
failed admin notification/recovery, unauthorized approval rejection, a permitted
publication, stale approval replay, second publication denial and a fresh incoming
invitation accepted by that same user. No real admin request or receiver acceptance
was sent during these tests. Live Telegram UI acceptance remains a separate check.

# Sender acceptance notification — 2026-11-03

Receiver acceptance now freezes `no_attempts` and queues one sender notification
atomically. The count is submitted by the browser, bounded to 0..1000000, and is
not an independently verified behavioral measurement. Old clients default to 0.
Local browser storage preserves counts through reload; unavailable storage falls
back to in-memory counting. Preview does not increment the count.

Validation: full suite with local Postman simulation: **83 passed in 33.56s**.
Two additional tests pass for non-admin sender routing and additive schema migration
without retroactive notifications. Existing launch/bootstrap regressions are included.
Browser fixtures pass at 280/390/1280px, verifying 11 attempts survive reload and
both acceptance requests send 11 after an injected initial failure.
Postman exercises successful notification, explicit HTTP 500 recovery through a
recreated App/background worker, HTTP 403 terminal failure, and no additional send
on repeated acceptance. Request logs show actual mocked sendMessage traffic.

No real recipient acceptance or notification was triggered during these tests.
Persistent delivery can duplicate after a crash/timeout following upstream delivery
but before local success is recorded; ordinary repeated accepts are deduplicated.
The existing local Telegram mock was reused. Orbit identified sendMessage but its
schema lacked request/response details; the official Telegram method and installed
aiogram interface supplied them. Installed Postman CLI rejects `postman status`;
workspace/owner search was therefore skipped; no cloud artifacts were changed.

