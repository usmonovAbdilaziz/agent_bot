# Qadam — bitta taklif, bitta javob

Admin senderni tanlaydi. Sender ixtiyoriy rasm/video, ism va tavsif tayyorlaydi.
Receiver taklifni Telegram ichidagi sahifada ochadi. **Ha** → mushaklar →
**Tanlovingiz uchun rahmat!** → sahifa yopiladi. Bir martalik cheklov har bir
taklifga tegishli: shu odam keyin boshqa yangi havolani ham ochishi mumkin.
Oddiy `/start` sender bo‘lish uchun tasdiq taklif qiladi. Suhbat ochilmaydi.

## Ishga tushirish

macOS: `sh start.command`. Windows: `start.bat`. Yoki `python3 run.py`.
Windows uchun `agent_bot_windows.zip`ni **Extract All** bilan chiqaring va
`agent_bot/start.bat`ni ikki marta bosing. Python 3.11–3.13 (64-bit) topilmasa,
launcher Python.org dan tekshirilgan Python 3.13.17 installerini yuklab, joriy
foydalanuvchi uchun o‘rnatadi. Birinchi ochishda BOT_TOKEN, ADMIN_PHONE va
Tailscale o‘rnatilgan, ulangan va Funnel uchun ruxsat berilgan bo‘lishi kerak.
To‘liq Windows yo‘riqnomasi: `WINDOWS_README.txt`.
Launcher kutubxonalar, Tailscale Funnel, web server va botni birga boshqaradi.
Har safar virtual muhitdagi kerakli modullar tekshiriladi; modul yetishmasa,
kutubxonalar qayta o‘rnatiladi (internet kerak).
Birinchi ishga tushirishda `.env` ichida `BOT_TOKEN`, `ADMIN_PHONE` kerak.
Haqiqiy tokenlarni chatga yubormang.

Tailscale HTTPS manzili avtomatik olinadi; `WEBAPP_URL`ni ko‘chirish kerak emas.
Terminal va kompyuter ishlab turishi kerak. Ctrl+C hammasini yopadi.
Bir token uchun faqat bitta bot jarayonini ishga tushiring. Lokal port band bo‘lsa
`.env`dagi WEBAPP_PORTni bo‘sh portga almashtiring; ushbu kompyuterda 8081 ishlatilmoqda.

Windows’da eski nusxada `No module named 'dotenv'` chiqsa, `start.bat` turgan
papkada CMD ochib bajaring:

```bat
.venv\Scripts\python.exe -m pip install --force-reinstall -r requirements.txt
start.bat
```

`launch.py` o‘rniga `start.bat` yoki `run.py` orqali ishga tushiring.

## Admin

`/start` → ilk marta o‘z kontaktini tasdiqlash → **O‘zim / Boshqa raqam**.
Avval tasdiqlangan admin yangi versiyada ham saqlanadi.

- **O‘zim**: taklif yaratishni boshlaydi yoki tugallanmagan qoralamani davom ettiradi.
- **Boshqa raqam**: xalqaro telefon raqamini kiriting, masalan `+998901234567`.
  Senderga oddiy bot havolasini yuboring. U `/start` bosib, **Raqamimni tasdiqlash**
  orqali aynan o‘z kontaktini ulashadi. Tasdiqlangan raqam admin tanlagan raqamga
  mos kelsa taklif tayyorlaydi. Avval raqamini tasdiqlagan foydalanuvchi tanlansa,
  bot unga yaratish bosqichini yuboradi.
- **Sender so‘rovlari**: kutilayotgan so‘rovlarni ko‘rsatadi. **Ruxsat berish**
  foydalanuvchi tanlagan 1, 10 yoki 30 ta havola uchun huquq beradi; **Rad etish** so‘rovni yopadi.
  Eski qaror tugmasini takror bosish qo‘shimcha ruxsat bermaydi.

## Sender bo‘lish so‘rovi

Oddiy `/start` → **Yuboruvchi bo‘lib ro‘yxatdan o‘tish** → o‘z telefon kontaktini
ulashish → 1, 10 yoki 30 ta tanlash → admin tasdig‘i → foydalanuvchiga xabar.
So‘ng `/start` bilan taklif yaratish boshlanadi. Admin raqam orqali tayinlagan bo‘lsa
**Admin raqamim orqali tanlagan** tugmasi ishlatiladi.

Admin tasdig‘i tanlangan miqdorda, raqam orqali tayinlash esa bitta ruxsat beradi.
Har bir tayyor havola yaratilganda bitta ruxsat sarflanadi. Qoralamani tahrirlash yoki `/cancel`
qilish ruxsatni sarflamaydi; eski kontaktni qayta yuborish uni yangilamaydi.
Adminning o‘zi yaratadigan takliflarga bu cheklov qo‘llanmaydi.

Telefonini tasdiqlagan foydalanuvchi `/taklif` orqali g‘oyasini matn qilib yuborishi
mumkin. Admin uni ko‘rib ma’qullasa, bitta qo‘shimcha havola ruxsati beriladi.

So‘rov, ruxsat va qoralama restartdan keyin ham saqlanadi. Xabar yuborishda
vaqtinchalik uzilish bo‘lsa navbatdan qayta yuboriladi. Tayyor havola xabari
yetib bormagan bo‘lsa `/start` aynan shu havolani qayta yetkazadi.

Telegram bot telefon raqamidan odamni qidirib topa olmaydi va botni ochmagan
odamga birinchi bo‘lib yozolmaydi. Shu sabab bir martalik kontakt tasdig‘i kerak.
Ro‘yxatdan o‘tish so‘rovida telefon raqami admin ko‘rishi uchun saqlanadi;
profilni taqqoslash uchun bot tokeni bilan HMAC ham saqlanadi.
Bot tokeni o‘zgarsa sender telefonini qayta tasdiqlash/tanlash kerak bo‘ladi.

## Sender

1. **Rasm / video**: rasm, MP4 video yoki dumaloq video xabar yuboring. Video
   60 soniyagacha, fayl 20 MiB gacha. Media kerak bo‘lmasa **Rasm/videosiz davom etish**.
2. **Ism**: Telegram full name avtomatik chiqadi. **Shu ismni qoldirish** yoki
   o‘zingiz yangi ism/matn yozing (1–120 belgi).
3. **Tavsif**: taklif matnini yuboring (1–2000 belgi).
4. **Ko‘rib chiqish**: media va matn chatda chiqadi. **Ko‘rinishini ochish** receiver
   sahifasining aynan o‘zini ko‘rsatadi. **Dizaynni tanlash** orqali Sodda, Romantik,
   Quvnoq yoki Nafis ko‘rinishni tanlang va preview orqali tekshiring. **Tahrirlash**
   bosqichlarni qayta ochadi.
5. **Tasdiqlash**: receiver uchun bitta bir martalik havola yaratadi. Adminning
   ikkinchi tasdig‘i yo‘q. Takror bosish yangi havola yaratmaydi.

Qoralama va bosqich SQLite bazasida saqlanadi. Uzilishdan keyin `/start` bilan
davom eting. `/cancel` tugallanmagan qoralamani bekor qiladi. Bu yordamchi buyruq
asosiy menyuga qo‘shilmagan.

## Receiver

Havola `https://t.me/BOT?start=i_TOKEN` ko‘rinishida. Birinchi receiver `/start`
bosganda havola unga birikadi. Bot faqat **Taklifni ochish** tugmasini yuboradi.
Telegram `/start` javobidan Mini Appni avtomatik ochishga ruxsat bermaydi:
foydalanuvchi bu tugmani bir marta bosadi.

Sahifada dumaloq media (agar bor bo‘lsa), ism, tavsif, **Ha / Yo‘q** turadi.
Video ovozsiz o‘ynaydi; **Ovozni yoqish** bilan ovoz yoqiladi. Yo‘q tugmasi
sichqoncha/teginish/klaviaturadan qochadi. Har 10 urinishda 😡 stiker ko‘rinishidagi
reaksiya vaqtincha chiqadi va urinishlar davom etadi. Telegramning yopish tugmasi
mavjud; rad etishga majburlovchi server amali yo‘q.

**Ha** faqat server javobni saqlagach bayram animatsiyasini chiqaradi va 2.8 soniyadan
keyin Telegram.WebApp.close() chaqiriladi. Eski klient yopishni bajarmasa sahifada
yopish tugmasi chiqadi. Aloqa uzilsa xatolik ko‘rsatiladi va qayta urinish mumkin.
Senderga **“Taklifingiz qabul qilindi! Oluvchi ‘Ha’ni bosdi”** hamda **“Yo‘q”ni
bosishga urinishlar soni** yuboriladi (bosilmasa 0). Qochadigan tugmaning har bir
qochishi bitta urinish hisoblanadi. Hisob shu qurilma/browserda saqlanadi; preview
hisoblanmaydi. Takroriy “Ha” odatda ikkinchi xabar yaratmaydi. Telegram vaqtincha
ishlamasa xabar bazadagi navbatdan qayta yuboriladi; botni bloklagan senderga
yuborish to‘xtatiladi. Yangi imkoniyatdan oldin qabul qilingan takliflar uchun
eski bildirishnomalar yuborilmaydi.
Keyingi yangi havoladagi `/start i_TOKEN` yangi taklifni ochadi, foydalanuvchi
oldin botni ishlatgan bo‘lsa ham. Oddiy `/start` ruxsatli senderning qoralamasini
davom ettiradi yoki sender bo‘lish taklifini ko‘rsatadi. Eski qabul qilingan
havola qayta ishlamaydi. Oddiy receiver matnlariga javob berilmaydi.

Havola odatda 48 soat amal qiladi. Egasi o‘z havolasini ishlatib yubormaydi.
Hali javob bermagan receiver eski taklif havolasini qayta ochsa, yangi HTTPS manzilli
tugma oladi. Eski xabardagi tugma eski manzilga bog‘langan.

## Tuzilma va xavfsizlik

- `main.py`: minimal Telegram oqimi; `config.py`: sozlamalar.
- `invitation_store.py`: atomik claim/accept, qoralamalar, rollar va q_* jadvallar.
- `react_src/`: receiver Mini App React komponentlari (media, tanlov, reaksiya va bayram holati).
- `web_minimal/`: React build natijasi; Python server shu tayyor, statik fayllarni uzatadi.
- `webapp.py`, `web_common.py`: receiver API va imzoli autentifikatsiya.
- `run.py`, `launch.py`: Tailscale Funnel HTTPS va jarayon boshqaruvi.
- `db.py`: umumiy SQLite yordamchilari va avvalgi sxemani saqlash.
- `legacy_bot.py`, `legacy_webapp.py`, `web/`: eski funksiyalar regressiya tekshiruvi va
  tiklash uchun arxiv. Amaldagi main.py bu menyu va marshrutlarni ishga tushirmaydi.

Eski bazadagi foydalanuvchilar va admin o‘chirilmaydi. Yangi versiya q_* jadvallarni
qo‘shadi. Eski relay sessiyalari va eski formatdagi rasm havolalari yangi oqimda
faollashtirilmaydi; ular bazada qoladi. Manbaning avvalgi nusxasi
`backups/source-before-minimal-20261103.zip` ichida.

API Telegram initData imzosi va 1 soatlik muddatni tekshiradi. Begona odam taklif
va mediani ololmaydi. Token/file_id browserga berilmaydi. Media server orqali
chegaralangan hajmda olinadi. Javob atomik/idempotent; hech qanday relay sessiya yo‘q.
`API_CONTRACT.md`da faol endpointlar keltirilgan.

## Testlar

```sh
npm install
npx playwright install chromium
npm run build
npm run test:ui
.venv/bin/python -m pytest -q
postman simulation run postman/simulations/telegram.sim.yaml --port 4629 --no-history
# Alohida terminal:
POSTMAN_TEST_URL=http://127.0.0.1:4629/telegram .venv/bin/python -m pytest -q
```

Yangi oqim `tests/test_minimal.py`da. HTTP testlar vaqtinchalik baza va soxta token
bilan ishlaydi; haqiqiy akkauntlarga xabar yubormaydi. UI sinovi Playwright o‘rnatilgan
muhitda `npm run test:ui`; `output/minimal/`da screenshotlar saqlanadi.
React frontendini tahrirlash uchun `react_src/`ni o‘zgartiring va `npm run build`ni
bajaring; natija avtomatik `web_minimal/`ga yoziladi. UI testida namunaviy ism/rasm
ishlatiladi, Telegram klienti simulyatsiya qilinadi.
Jonli Telegram, qurilmadagi yopilish va Tailscale Funnel alohida qabul sinovini talab qiladi.

ZIP uchun `python3 package.py`; tokenlar, baza va virtual muhit paketga kirmaydi.
Windows ZIP: `python3 package.py --windows`. Boshqa kompyuterda ayni bot tokeni
ishlayotgan bo‘lsa, Windows nusxasini ochishdan oldin uni to‘xtating.
# agent_bot
# agent_bot
