# Yakuniy tekshiruv va tuzatishlar

Sana: 2026-11-02. Loyiha: `/Users/munis/Documents/agent_bot`.

**Auditda topilgan uchta xato tuzatildi. Yangilangan bot ishga tushirildi.**
Barcha **33 ta avtomatik test o‘tdi**; kutilgan xato (`xfail`) qolmadi.

## Tuzatilgan kamchiliklar

| Oldingi holat | Hozirgi xulq | Dalil |
|---|---|---|
| Rasm tugmalarini yangilash xatosi sessiya ogohlantirishini to‘xtatardi | Ogohlantirish mustaqil yuboriladi. Har tomon uchun yetkazish holati bazada saqlanadi; restartdan keyin qayta uriniladi | `tests/test_recovery.py`: notice, restart va admin-request testlari |
| `quiet()` HTTP 403 ni yutardi | Barcha yuborishlar umumiy faol/blok tekshiruvi va Forbidden qayta ishlovidan o‘tadi. Bir necha foydalanuvchida ketma-ket 403 rekursiyasiz qayta ishlanadi | Forbidden notification cascade va control edit testlari |
| Admin `/stop` qilsa ham shikoyat nusxasi kelardi | Barcha media/nusxalar ham `/stop` ga bo‘ysunadi. Shikoyat navbatda qoladi va admin `/start` qilganda yetkaziladi | Stopped admin, restart va report-copy failure testlari |

Sessiya xabari ikkala tomon majburiy ogohlantirishni olmaguncha uzatilmaydi.
Yetkazilmagan shikoyat uchun admin menyusida **Shikoyatlarni yetkazish** tugmasi bor.
Bazada suhbat matni saqlanmaydi: yangi navbatlarda faqat Telegram IDlar va holatlar bor.

## Sender va receiver uchun tushunarli menyu

- **Senderni taklif qilish** oddiy bot kirish havolasini beradi. Taklif qilingan odam `/start` bosib rasm yuboradi; unga admin huquqi berilmaydi.
- **Receiver havolasi yaratish** avval rasm, so‘ng tasdiq so‘raydi. Moderatsiya yoqilgan bo‘lsa, admin tasdig‘idan keyin havola yaratiladi.
- Receiver alohida akkaunt sifatida yaratilmaydi: bir martalik rasm havolasini birinchi ochgan odam oluvchi bo‘ladi.
- **Sender / receiver** yordam oynasi va README da ketma-ket qadamlar bor.

Yangi tugma mavjud atomik havola, moderatsiya va rozilik oqimidan foydalanadi.
Alohida ruxsat berish mexanizmi yoki Mini App qo‘shilmadi.

## Tekshiruvlar

`POSTMAN_TEST_URL=http://127.0.0.1:4618/telegram .venv/bin/python -m pytest -q --tb=short`

**33 passed in 16.41s.** Haqiqiy aiogram Dispatcher, HTTP so‘rovlari va vaqtinchalik SQLite bilan bajarildi. Postman loglarida getUpdates, sendPhoto, copyMessage va editMessageReplyMarkup so‘rovlari bor. Asl 22 test va 11 ta yangi regressiya/oqim testi o‘tdi.

`pip check`, Python kompilyatsiyasi va `sh -n start.command` ham xatosiz.

Eski baza uchun yangi jadvallarni qo‘shish, mavjud admin/sessiyalarni saqlash va migratsiyani qayta bajarish testi o‘tdi. Ishga tushirishdan oldin lokal bazaning SQLite backupi va avvalgi ZIP `backups/` da saqlandi; tarqatiladigan ZIPga kiritilmaydi.

## Haqiqiy Telegramda kuzatilgan holat

Foydalanuvchining joriy roziligi bilan eski polling to‘xtatildi va yangilangan **@Qadam_n1_bot** ishga tushirildi. Yangi sender/receiver menyusi bilan oxirgi ishga tushish: **18:32:35, Asia/Tashkent**.

Bazani faqat o‘qish orqali tekshirganda:

- admin tasdiqlangan;
- 2 ta foydalanuvchi;
- 1 ta havola ishlatilgan;
- 1 ta rasm yetkazilgan;
- 1 ta sessiya ochiq;
- ikkala tomonning sessiya ogohlantirishi yetkazilgan.

Foydalanuvchi `/start` javobini chatda ham tasdiqladi. Bu jonli rasm → havola → rozilik → sessiya oqimining dalili. Matn/ovozli relay, uchinchi hisobning admin so‘rovi, shikoyat va bloklashning to‘liq jonli qabul sinovi shu holat kesimida hali tasdiqlanmagan; ular avtomatik testlarda o‘tgan.

## Chegaralar

Telegram yetkazishi va SQLite commit o‘rtasidagi uzilishda tarmoq bo‘ylab mutlaq exactly-once kafolati yo‘q. Atomik havola claim esa 40 parallel ulanish bilan tekshirilgan. Telegramdan o‘chirilgan yoki nusxalab bo‘lmaydigan xabarning shikoyat nusxasini qayta olish kafolatlanmaydi; shikoyat IDlari saqlanadi.

Bot shu kompyuterda long polling bilan ishlaydi. Kompyuter uxlab qolsa yoki o‘chsa, bot javob bermaydi. Doimiy serverga deploy bu ishda bajarilmadi.

## ZIPning alohida tekshiruvi

Tayyor arxiv yangi vaqtinchalik papkaga ochildi va uning ichidagi kod ustida Postman bilan barcha testlar bajarildi: **33 passed in 16.79s**. ZIP CRC butunligi va haqiqiy BOT_TOKEN arxivdagi hech bir faylda yo‘qligi tekshirildi. Yakuniy qayta yig‘ishda faqat ushbu natija hujjatlarga qo‘shildi; tekshirilgan dastur kodi o‘zgarmadi.
