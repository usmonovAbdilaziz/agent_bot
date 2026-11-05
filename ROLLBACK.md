# Deploy va qaytarish

Prod deployeri `deploy/poll-deploy.py` `main` dagi aynan commit uchun Verify muvaffaqiyatini kutadi, so‘ng image quradi. `ENABLE_CEREMONY` standart `false`; server `/home/ubuntu/apps/agent_bot/.env` faylidan o‘qiydi. O‘zgartirishlar server operatori tomonidan alohida bajariladi.

## Deploy oldidan

1. Diskda yetarli joy va ishlaydigan backup mavjudligini, dastur migratsiyasi eski sxemani yangilashini va qaytarishdagi ma’lumot yo‘qolishi xavfini tekshiring.
2. Ishlayotgan konteynerdagi bazaning tranzaksion nusxasini oling (fayl bind mount orqali host `data/` katalogiga tushadi):

```sh
docker exec qadam-agent python -c 'import sqlite3; a=sqlite3.connect("/app/data/bot.sqlite3"); b=sqlite3.connect("/app/data/manual-before-release.sqlite3"); a.backup(b); b.close(); a.close()'
```

Bu nomni qayta ishlatishdan oldin avvalgi zaxirani saqlang. Avtomatik deployer ham har commitga `backup-before-<sha>.sqlite3` yaratadi. Yangi konteyner ishga tushganda `InvitationDB.init()` qo‘shimcha migratsiyalarni bajaradi; zaxira bundan oldin olinadi.

## Deployni tekshirish

`main` dagi Verify aynan yangi SHA uchun muvaffaqiyatini tekshiring. `curl -fsS https://api.unumdor.uz/bot/healthz` `ready: true` qaytarishi, `/bot/assets/app.js` SHA-256 xeshi shu commitdagi `web_minimal/app.js` xeshiga mos bo‘lishi kerak. So‘ng alohida test hisoblarida fun taklif yaratib oching; ceremony flag yoqilgandagina ceremony sinovini bajaring. Qurilma natijalarini `DEVICE_CHECKLIST.md`ga yozing.

## Qaytarish

Avtomatik rollback health muvaffaqiyatsiz bo‘lsa avvalgi konteynerni qayta ishga tushiradi, ammo bazani avtomatik qaytarmaydi. Rejalashtirilgan qaytarishda eski kod commitini `main`ga revert orqali qaytaring va Verify/deployni kuting; ishlab turgan konteynerni to‘xtatmasdan SQLite fayllarini almashtirmang. Kerak bo‘lsa servisni to‘xtatib, bazani tanlangan backupdan SQLite backup API bilan tiklang; tegishli WAL/SHM fayllari faqat barcha ulanishlar yopilgandan keyin ko‘rib chiqilsin. Tiklash backupdan keyingi RSVP va boshqa yozuvlarni yo‘qotadi: ulardan avval alohida nusxa oling va ma’lumotlarni qayta tiklash rejasini belgilang. So‘ng eski kodni ishga tushirib health va test taklifni tekshiring. Eski kod yangi sxemani ishga tushirish testi `tests/test_m7_release.py`da; bu eski kod barcha yangi ma’lumotlarni tushunishini kafolatlamaydi.

Operator, barcha SQLite ulanishlari to‘xtatilganini va to‘g‘ri zaxira tanlanganini tasdiqlagandan keyin tiklash namunasi:

```sh
sudo systemctl stop qadam-deploy.timer
docker stop -t 30 qadam-agent
sudo -u ubuntu python3 -c 'import sqlite3; a=sqlite3.connect("/home/ubuntu/apps/agent_bot/data/manual-before-release.sqlite3"); b=sqlite3.connect("/home/ubuntu/apps/agent_bot/data/bot.sqlite3"); a.backup(b); b.close(); a.close()'
```

Shundan so‘ng eski kodning tekshirilgan konteynerini deployer sozlamalariga mos qayta yarating, health va test taklifni tekshiring, keyin `sudo systemctl start qadam-deploy.timer` bilan timerni tiklang. Timer qayta ishga tushishidan avval `main` qaytarilgan commitni ko‘rsatishi kerak, aks holda u yangi versiyani yana o‘rnatadi.
