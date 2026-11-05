# M6 sifat tekshiruvi

- RSVP: Toshkent kuni tugagach yangi javob rad etiladi; eski javob ko‘rinadi va idempotent qaytadi. Sender xabarida taklif raqami bor.
- A3: document sifatidagi rasm qabul qilinmaydi (`App.message`, `media` / `c_media`); foydalanuvchi belgilagan shartga ko‘ra kichraytirish va Pillow kerak emas.
- 500 javob: 250 sahifa va har xabarning 4096 belgidan kamligi sinovdan o‘tdi.
- M0 oldi, M0, M1 va M4 oldingi tarixiy SQLite sxemalari ikki marta migratsiya qilindi; eski takliflar ochildi.
- 12 dizayn, to‘rt ekran va yetti holat: 336 screenshot; geometriya tekshiruvida tugmalar kesilishi yoki bir-biriga kirishi yo‘q. Kontakt varaqlari ko‘rib chiqildi.
- Kontrast: barcha dizaynlarda panel, token va asosiy tugma 4.5:1 dan yuqori (eng past o‘lchov 5.47:1).
- Chromium accessibility tree, tugma nomlari, fokus va Tab, sender preview, fun, ceremony, RSVP va envelope klaviatura yo‘llari o‘tdi. Bu avtomatlashtirilgan tekshiruv ekranni o‘qish dasturidagi real qurilma auditining o‘rnini bosmaydi.
- Reduced motion: confetti, hearts, balloons, neon-glow, snow, titrash, glitch, envelope va kirish animatsiyasi tekshirildi.
- 4x CPU: confetti 60.0 FPS/80 zarracha; hearts 59.2/80; balloons 60.0/60; neon-glow 60.0/80; snow 60.0/80. Natijalar lokal Chromium muhitiga xos.
- Xavfsizlik: bot preview escape, Mini App matn rendering, map host/scheme, barcha invite endpointlarda noto‘g‘ri initData va begona foydalanuvchini rad etish tekshirildi.
- Postman simulyatsiyasi bilan 198 ta Python testi o‘tdi. Tez accessibility/contrast/motion CI’da, screenshot va performance workflow_dispatch jobida.
- Topilmalar: o‘rta — marosim sanasidan keyin yangi RSVP ochiqligi tuzatildi; past — Telegram document rasmi qabul qilinmaydi, mavjud mahsulot xatti-harakati sifatida saqlandi. Qurilma va screen reader tekshiruvlari kutilmoqda.
