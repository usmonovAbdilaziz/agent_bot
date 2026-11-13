# Deploy va qaytarish

Prod `main` uchun Verify muvaffaqiyatidan keyin `deploy/poll-deploy.py` SQLite backup olib image o‘rnatadi. Bu hujjatdagi buyruqlarni faqat operator bajaradi. Barcha baza ulanishlari to‘xtatilganini tekshiring; `qadam-deploy.timer` va botni to‘xtating. Tiklashdan keyin backup olingan paytdan keyingi yozuvlar yo‘qoladi.

## Validatsiyalangan zaxira

Repository checkoutdan, fayl hali mavjud bo‘lmagan noyob nom bilan:

```sh
sudo -u ubuntu python3 scripts/sqlite_safe_backup.py backup /home/ubuntu/apps/agent_bot/data/bot.sqlite3 /home/ubuntu/apps/agent_bot/data/manual-before-release.sqlite3
```

Skript manbani faqat `mode=ro` bilan ochadi, mavjudlik, `PRAGMA integrity_check` va `settings`, `users`, `q_invites` jadvallarini tekshiradi. Noto‘g‘ri manba yoki mavjud chiqish faylida to‘xtaydi. Avtomatik deployerning `backup-before-<sha>.sqlite3` nusxasi ham bor; u bot to‘xtashidan oldin olingani uchun undan keyingi yozuvlarni o‘z ichiga olmaydi.

## Deploy tekshiruvi

Migratsiya yangi konteyner `InvitationDB.init()`da ishlaydi, deployerdagi backup undan oldin olinadi. Verify aynan yangi SHA uchun o‘tganini, `curl -fsS https://api.unumdor.uz/bot/healthz` `ready: true` ekanini va `/bot/assets/app.js` SHA-256 xeshi release `web_minimal/app.js` bilan tengligini tekshiring. Alohida hisoblarda test taklif yarating. `ENABLE_CEREMONY` `/home/ubuntu/apps/agent_bot/.env`da; `docker restart` env faylini qayta o‘qimaydi.

## Qaytarish

Avtomatik health rollback kodni qaytaradi, bazani tiklamaydi. Operator eski kodni `main`da revert qilib, yozuvlarni to‘xtatadi. Barcha ulanishlar yopilgach tanlangan backupdan tiklash, avtomatik deployerni to‘xtatish va mustaqil joriy nusxa olish:

```sh
sudo systemctl stop qadam-deploy.timer
docker stop -t 30 qadam-agent
sudo -u ubuntu python3 scripts/sqlite_safe_backup.py restore /home/ubuntu/apps/agent_bot/data/manual-before-release.sqlite3 /home/ubuntu/apps/agent_bot/data/bot.sqlite3 --safety /home/ubuntu/apps/agent_bot/data/before-restore.sqlite3
```

Skript avval backupni tekshiradi, so‘ng joriy bazaning yangi mustaqil nusxasini majburiy oladi va faqat keyin tiklaydi. Nomi oldin mavjud bo‘lsa to‘xtaydi. Eski kod konteynerini qayta yarating, health va test taklifni tekshiring; `main` qaytarilgan commitda ekanini tasdiqlab, `sudo systemctl start qadam-deploy.timer` bilan timerni qayta yoqing.
