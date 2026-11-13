# Alohida test muhiti

Test uchun BotFather orqali alohida bot yarating. Ishlayotgan bot tokenini ishlatmang: ikki polling jarayoni bir tokenda ishlay olmaydi. Ushbu loyiha boshqa serverdagi tokenni tekshira olmaydi; tokenlar har xil ekanini ishga tushirishdan oldin o'zingiz tasdiqlang. BotFather tokenini chatga yubormang.

`.env.test` faylini faqat test tokeni va admin telefoni bilan to'ldiring. `DB_PATH` alohida SQLite fayl, `WEBAPP_URL` esa sinov uchun alohida ochiq HTTPS manzili bo'lsin. `WEBAPP_PORT` mavjud xizmat portidan farq qilsin. `.env.test` gitignore qilingan; ruxsatini `chmod 600 .env.test` bilan cheklang. O'z HTTPS reverse proxy'ingizda test domenini `127.0.0.1:8081` ga yo'naltiring. Asl bot, baza, domen va portdan foydalanmang.

Loyiha papkasida Python 3.11–3.13 virtual muhitini yarating va `pip install -r requirements.txt` bajaring. Qo'lda ishga tushirish: `.venv/bin/python start_staging.py`. Skript `.env.test` dagi sozlamalarni ishlatadi, asosiy `.env` ni yuklamaydi va `data/bot.sqlite3` standart bazasini rad etadi. Boshqa joydagi haqiqiy baza yo'lini tanlamaslik foydalanuvchi mas'uliyatida.

Systemd uchun `deploy/qadam-staging.service.example` nusxasidagi foydalanuvchi va mutlaq yo'llarni o'zgartirib, serveringizda alohida `qadam-staging.service` sifatida o'rnating; keyin `systemctl daemon-reload` va `systemctl enable --now qadam-staging` ishlating. Bu namunani o'zi deploy qilmaydi. HTTPS va port xavfsizlik devori sozlamalarini serveringizga moslang.

Telegramda yangi botga `/start` yuboring va `.env.test` dagi admin raqamiga tegishli shaxsiy kontaktingizni Telegram tugmasi bilan ulashing. Admin menyusidan `O‘zim` tanlansa sender oqimi boshlanadi; `Boshqa raqam` esa boshqa foydalanuvchiga ruxsat berish uchun. Ikkinchi hisob bilan taklif havolasini oching. Qayta sinashda yangi taklif yarating.
