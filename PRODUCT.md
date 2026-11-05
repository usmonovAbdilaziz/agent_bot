# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Admin tanlagan sender va bir martalik taklifni ochadigan receiver.

## Product Purpose
Ixtiyoriy rasm yoki 1 daqiqagacha video, Telegramdan olingan tahrirlanadigan ism va
majburiy tavsif bilan shaxsiy taklif. Receiver Ha desa rahmat va mushaklar,
sahifa yopiladi. Bir martalik holat taklifga bog‘langan; yangi havola oldingi
receiverga ham ishlaydi. Oddiy /start sender bo‘lishni tasdiqlashni taklif qiladi.

## Operating Context
Python aiogram, SQLite, aiohttp, ngrok HTTPS. Bitta polling jarayoni.
Telegram initData imzosi serverda tekshiriladi. UI o‘zbekcha lotin yozuvida.

## Capabilities and Constraints
Admin menyusi: O‘zim / Boshqa raqam / Sender so‘rovlari. Foydalanuvchi sender
bo‘lishni tasdiqlasa, admin ruxsati so‘raladi. Tasdiq bitta havola uchun amal qiladi.
Raqam orqali tanlangan sender o‘z kontaktini tasdiqlaydi; bu ruxsat ham bir martalik.
Sender chatdagi ketma-ket bosqichlardan o‘tadi; brauzerda parallel yaratish formasi yo‘q.
Tasdiqlash yagona havola yaratadi. Media optional, video <=60 soniya va <=20 MiB.
Receiver tartibi: to‘liq ekran fon media yoki gradient, uning ustida title, description va Ha/Yo‘q. Matn joyi yuqori, o‘rta yoki past.
Yo‘q qochadi; har 10 urinishda vaqtinchalik 😡 chiqadi, so‘ng davom etadi.
Ha atomik ravishda yakunlaydi; suhbat, relay va qo‘shimcha moderatsiya ochilmaydi.
Telegram /startdan avtomatik browser ochmaydi: bitta Taklifni ochish tugmasi kerak.

## Evidence on Hand
Yangi oqim uchun real Dispatcher/lokal HTTP testlar; Postman mocki; Playwright
fixture sinovlari. Jonli Telegramdagi yakuniy tekshiruv lokal testlardan alohida.
