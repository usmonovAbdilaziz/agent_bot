QADAM BOT — WINDOWSDA ISHGA TUSHIRISH

1. ZIP ustiga o‘ng tugma bosing → Extract All / Извлечь всё.
2. Chiqarilgan agent_bot papkasidagi start.bat ni ikki marta bosing.
3. Birinchi ochishda internet bo‘lsin. Python kerak bo‘lsa python.org dan
   yuklanib joriy foydalanuvchi uchun o‘rnatiladi. Kutubxonalar ham o‘rnatiladi.
4. Oyna so‘raganda quyidagilarni kiriting:
   - BOT_TOKEN: BotFather bergan bot tokeni.
   - ADMIN_PHONE: adminning Telegram telefon raqami (+998... shaklida).
   Tailscale o‘rnatilgan, hisobga kirilgan va Funnelga ruxsat berilgan bo‘lsin.
   Token belgilarining ko‘rinmasligi normal: joylashtiring va Enter bosing.
5. “To‘liq ishga tushdi” yozuvini kuting. Telegramda botga /start yuboring.
   Birinchi admin o‘z telefon kontaktini tasdiqlaydi.

Keyingi safar faqat start.bat ni bosing. Sozlamalar .env da saqlanadi.
Tailscale HTTPS manzilini launcher o‘zi oladi; qo‘lda ko‘chirish kerak emas.
Bot, Mini App va Funnel birga ishlaydi. To‘xtatish: shu oynada Ctrl+C.
Oyna ochiq, kompyuter va internet ishlab turishi kerak.

Talab: 64-bit Windows 10/11 va internet. PowerShell Windows tarkibida mavjud.
Avtomatik Python o‘rnatish joriy foydalanuvchi uchun bajariladi; tizim PATH
sozlamalari o‘zgartirilmaydi. Korporativ cheklovlar o‘rnatishni bloklasa,
Python 3.13 (64-bit) ni o‘rnating va start.bat ni qayta oching.

MUHIM: ayni BOT_TOKEN bilan boshqa kompyuterdagi botni avval to‘xtating.
Bir botni ikki kompyuterda parallel polling bilan ishlatmang.

Mavjud loyihani yangilash:
- Eski botni Ctrl+C bilan to‘xtating.
- Yangi manba fayllarini o‘sha papkaga ko‘chiring.
- .env va data papkasini saqlang. Ularni o‘chirmang.
- Boshqa kompyuterdan .venv va .runtime ni ko‘chirmang.
- Oldingi foydalanuvchi/taklif holatini ham ko‘chirmoqchi bo‘lsangiz, eski bot
  to‘xtagach data papkasini yangi kompyuterga ko‘chiring. ZIPda baza yo‘q.

Xatolik bo‘lsa oyna ochiq qoladi. Tokenlarni yubormasdan xato matnini yuboring.
start.bat ni ZIP ichidan ishlatmang; launch.py ni alohida ochmang.

Paket token, haqiqiy telefon raqami, baza va virtual muhitni o‘z ichiga olmaydi.
Windowsdagi haqiqiy ikki bosish/o‘rnatish sinovi macOSda bajarilmagan.
