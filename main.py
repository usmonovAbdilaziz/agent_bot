"""Qadam: admin -> sender wizard -> one receiver -> thank you."""
import asyncio
import contextlib
import hashlib
import hmac
import html
import logging
import re
import time
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo, MenuButtonCommands)
from config import Config
from invitation_store import InvitationDB

MAX_MEDIA = 20 * 1024 * 1024

def select_photo(photos):
    suitable = [photo for photo in photos if min(photo.width, photo.height) >= 360]
    if suitable:
        return min(suitable, key=lambda photo: photo.width * photo.height)
    return max(photos, key=lambda photo: photo.width * photo.height)

def esc(value):
    return html.escape(str(value or ''))

def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label,callback_data=data) for label,data in row] for row in rows])

def phone(value):
    digits = re.sub(r'\D','',value)
    return digits if 8 <= len(digits) <= 15 else None

class App:
    def __init__(self, bot, db, cfg, username):
        self.bot, self.db, self.cfg, self.username = bot, db, cfg, username
        self.lock = asyncio.Lock()
        self.notice_lock = asyncio.Lock()
        self.ready = False

    async def admin(self):
        value = await self.db.setting('admin')
        return int(value) if value else None

    def phone_hash(self, value):
        return hmac.new(self.cfg.token.encode(),value.encode(),hashlib.sha256).hexdigest()

    async def is_sender(self, uid):
        return uid == await self.admin() or bool(await self.db.one('SELECT 1 FROM q_senders WHERE uid=?',(uid,)))

    async def call(self, uid, method, **kwargs):
        for attempt in range(2):
            try:
                return await method(chat_id=uid, **kwargs)
            except TelegramForbiddenError:
                await self.db.run('UPDATE users SET active=0 WHERE tg_id=?',(uid,))
                return None
            except TelegramRetryAfter as exc:
                if attempt or exc.retry_after > 3: raise
                await asyncio.sleep(exc.retry_after)

    async def send(self, uid, text, **kwargs):
        return await self.call(uid,self.bot.send_message,text=text,**kwargs)

    async def notify_acceptance(self, mid):
        async with self.notice_lock:
            notice = await self.db.one("SELECT 1 FROM q_accept_notices WHERE invite_id=? AND status='pending'", (mid,))
            if not notice:
                return
            item = await self.db.invite(mid)
            text = (f'✅ <b>Taklifingiz qabul qilindi!</b>\n'
                    f'Taklif #{mid}: {esc(item["title"])}\n'
                    f'Oluvchi “Ha”ni bosdi.\n'
                    f'“Yo‘q”ni bosishga urinishlar: <b>{item["no_attempts"]} marta</b>.')
            try:
                sent = await asyncio.wait_for(self.send(item['sender'], text), timeout=10)
            except (TelegramAPIError, OSError, TimeoutError) as exc:
                logging.warning('Sender xabari keyinroq yuboriladi: %s', type(exc).__name__)
                return
            await self.db.run('UPDATE q_accept_notices SET status=? WHERE invite_id=?',
                              ('sent' if sent else 'failed', mid))

    async def acceptance_notifications(self):
        while True:
            try:
                notices = await self.db.all("SELECT invite_id FROM q_accept_notices WHERE status='pending' ORDER BY invite_id LIMIT 20")
                for notice in notices:
                    await self.notify_acceptance(notice['invite_id'])
                requests = await self.db.all("SELECT id FROM q_sender_requests WHERE (status='pending' AND admin_notified=0) OR (status!='pending' AND decision_notified=0) ORDER BY id LIMIT 20")
                for request in requests:
                    await self.notify_sender_request(request['id'])
                suggestions = await self.db.all("SELECT id FROM q_suggestions WHERE (status='pending' AND admin_notified=0) OR (status!='pending' AND decision_notified=0) ORDER BY id LIMIT 20")
                for suggestion in suggestions:
                    await self.notify_suggestion(suggestion['id'])
            except Exception as exc:
                logging.error('Sender xabari navbati: %s', type(exc).__name__)
            await asyncio.sleep(15)

    def web_button(self, label, mid):
        return InlineKeyboardButton(text=label,web_app=WebAppInfo(url=self.cfg.webapp_url+'/?'+urlencode({'invite':mid})))

    async def home(self, uid):
        if uid == await self.admin():
            await self.send(uid,'<b>Kim taklif yuboradi?</b>',reply_markup=kb(
                [('O‘zim','q:self'),('Boshqa raqam','q:phone')],
                [('Sender so‘rovlari','q:requests'),('Takliflar','q:ideas')]))
        elif await self.is_sender(uid):
            flow = await self.db.flow(uid)
            if flow: await self.prompt(uid)
            else:
                await self.db.begin(uid)
                await self.prompt(uid)
        elif not await self.admin():
            await self.contact_prompt(uid)
        else:
            pending = await self.db.one("SELECT id FROM q_sender_requests WHERE uid=? AND status='pending'",(uid,))
            if pending:
                await self.notify_sender_request(pending['id'])
                await self.send(uid,'Sender bo‘lish so‘rovingiz admin tasdig‘ini kutmoqda.')
            else:
                registration=await self.db.one('SELECT phone FROM q_registration WHERE uid=?',(uid,))
                if registration and registration['phone']:
                    return await self.send(uid,'Nechta taklif yubormoqchisiz?',reply_markup=kb(
                        [('1 ta','q:quota:1'),('10 ta','q:quota:10'),('30 ta','q:quota:30')]))
                await self.send(uid,'Yuboruvchi bo‘lish uchun ro‘yxatdan o‘ting.',
                    reply_markup=kb([('Yuboruvchi bo‘lib ro‘yxatdan o‘tish','q:request')],
                                    [('Hozir emas','q:later')],
                                    [('Admin raqamim orqali tanlagan','q:contact')]))

    async def notify_sender_request(self, request_id, force=False):
        async with self.notice_lock:
            row = await self.db.one('SELECT * FROM q_sender_requests WHERE id=?',(request_id,))
            if not row: return
            pending = row['status']=='pending'
            column = 'admin_notified' if pending else 'decision_notified'
            if row[column] and not (pending and force): return
            if pending:
                target = await self.admin()
                if not target: return
                profile = await self.db.one('SELECT full_name FROM q_profiles WHERE uid=?',(row['uid'],))
                name = profile['full_name'] if profile else str(row['uid'])
                text = f'<b>Sender bo‘lish so‘rovi #{row["id"]}</b>\n{esc(name)} (ID: {row["uid"]})\nTelefon: {esc(row["phone"] or "avvalgi so‘rov")}\nSo‘ralgan havolalar: {row["quantity"]} ta'
                markup = kb([('Ruxsat berish',f'q:approve:{row["id"]}'),('Rad etish',f'q:deny:{row["id"]}')])
            else:
                target = row['uid']
                if row['status']=='approved':
                    text = f'✅ Admin {row["quantity"]} ta taklif havolasini yaratishga ruxsat berdi. Boshlash uchun /start bosing.'
                else:
                    text = 'Admin sender bo‘lish so‘rovingizni rad etdi. Keyinroq /start orqali qayta so‘rashingiz mumkin.'
                markup = None
            try:
                sent = await asyncio.wait_for(self.send(target,text,reply_markup=markup),timeout=10)
            except (TelegramAPIError,OSError,TimeoutError) as exc:
                logging.warning('Sender so‘rovi xabari keyinroq yuboriladi: %s',type(exc).__name__)
                return
            if sent or not pending:
                await self.db.run(f'UPDATE q_sender_requests SET {column}=1 WHERE id=?',(request_id,))

    async def request_sender(self, uid):
        if await self.is_sender(uid): return await self.home(uid)
        if not await self.admin():
            return await self.send(uid,'Admin hali sozlanmagan. Keyinroq /start bosing.')
        pending=await self.db.one("SELECT id FROM q_sender_requests WHERE uid=? AND status='pending'",(uid,))
        if pending:
            return await self.send(uid,'So‘rovingiz admin tasdig‘ini kutmoqda.')
        await self.db.run("INSERT OR IGNORE INTO q_registration(uid,phone) VALUES(?,'')",(uid,))
        await self.contact_prompt(uid)

    async def decide_sender(self, q, request_id, approve):
        uid = await self.db.decide_sender(request_id,q.from_user.id,approve)
        if uid is None:
            return await self.send(q.from_user.id,'Bu so‘rov allaqachon ko‘rib chiqilgan yoki ruxsat berib bo‘lmaydi.')
        await self.notify_sender_request(request_id)
        await self.send(q.from_user.id,'So‘ralgan miqdor uchun ruxsat berildi.' if approve else 'So‘rov rad etildi.')
        try:
            await self.bot.edit_message_reply_markup(chat_id=q.from_user.id,message_id=q.message.message_id,reply_markup=None)
        except TelegramAPIError:
            pass

    async def contact_prompt(self, uid):
        await self.send(uid,'O‘z telefon raqamingizni pastdagi tugma orqali ulashing. Raqamingiz so‘rov bilan adminga yuboriladi.',reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text='Raqamimni tasdiqlash',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True))

    async def contact(self, m):
        uid, number = m.from_user.id, phone(m.contact.phone_number)
        if m.contact.user_id != uid or not number:
            await self.send(uid,'Pastdagi tugma orqali faqat o‘z raqamingizni yuboring.')
            return
        digest = self.phone_hash(number)
        admin = await self.admin()
        if not admin and number == self.cfg.admin_phone:
            await self.db.set_setting('admin',uid)
            await self.send(uid,'Admin tasdiqlandi.',reply_markup=ReplyKeyboardRemove())
            await self.home(uid)
            return
        # Only Telegram's self-contact can bind a number to an account.
        await self.db.run('UPDATE q_profiles SET phone_hash=NULL WHERE phone_hash=? AND uid!=?',(digest,uid))
        await self.db.run('UPDATE q_profiles SET phone_hash=? WHERE uid=?',(digest,uid))
        if await self.db.redeem_phone(uid,digest):
            await self.send(uid,'Raqamingiz tasdiqlandi.',reply_markup=ReplyKeyboardRemove())
            await self.db.begin(uid)
            await self.prompt(uid)
        elif uid == admin:
            await self.home(uid)
        else:
            await self.send(uid,'Raqamingiz saqlandi.',reply_markup=ReplyKeyboardRemove())
            registration=await self.db.one('SELECT uid FROM q_registration WHERE uid=?',(uid,))
            if registration:
                await self.db.run('UPDATE q_registration SET phone=? WHERE uid=?',('+'+number,uid))
                return await self.send(uid,'Nechta taklif yubormoqchisiz?',reply_markup=kb(
                    [('1 ta','q:quota:1'),('10 ta','q:quota:10'),('30 ta','q:quota:30')]))
            await self.home(uid)

    async def notify_suggestion(self, suggestion_id, force=False):
        async with self.notice_lock:
            row=await self.db.one('SELECT * FROM q_suggestions WHERE id=?',(suggestion_id,))
            if not row: return
            pending=row['status']=='pending'
            column='admin_notified' if pending else 'decision_notified'
            if row[column] and not (pending and force): return
            if pending:
                target=await self.admin()
                if not target: return
                profile=await self.db.one('SELECT full_name FROM q_profiles WHERE uid=?',(row['uid'],))
                name=profile['full_name'] if profile else str(row['uid'])
                text=f'<b>Taklif #{row["id"]}</b>\n{esc(name)} (ID: {row["uid"]})\n\n{esc(row["body"])}'
                markup=kb([('1 ta ruxsat berish',f'q:idea_yes:{row["id"]}'),('Rad etish',f'q:idea_no:{row["id"]}')])
            else:
                target=row['uid']
                text=('✅ Taklifingiz ma’qullandi. Sizga 1 ta havola yaratish huquqi berildi. /start' if row['status']=='approved'
                      else 'Taklifingiz ko‘rib chiqildi, hozircha ma’qullanmadi.')
                markup=None
            try:
                sent=await asyncio.wait_for(self.send(target,text,reply_markup=markup),timeout=10)
            except (TelegramAPIError,OSError,TimeoutError) as exc:
                logging.warning('Taklif xabari keyinroq yuboriladi: %s',type(exc).__name__)
                return
            if sent or not pending:
                await self.db.run(f'UPDATE q_suggestions SET {column}=1 WHERE id=?',(suggestion_id,))

    async def choose_phone(self, uid, value):
        number = phone(value)
        if not number or not re.fullmatch(r'\+?[\d\s()\-]+',value):
            await self.send(uid,'Raqamni xalqaro formatda kiriting. Masalan: +998901234567')
            return
        digest = self.phone_hash(number)
        target = await self.db.grant_phone(digest)
        await self.db.run('DELETE FROM q_flows WHERE uid=?',(uid,))
        if target:
            await self.db.begin(target)
            await self.prompt(target)
        await self.send(uid,'Sender bitta havola uchun tanlandi. U ushbu bot havolasini ochib, /start bosadi va kerak bo‘lsa raqamini tasdiqlaydi:\n'
            f'https://t.me/{self.username}',reply_markup=kb([('Yangi taklif','q:home')]))

    async def prompt(self, uid):
        flow = await self.db.flow(uid)
        if not flow: return await self.home(uid)
        mid = flow['invite_id']
        if flow['stage']=='phone':
            return await self.send(uid,'Senderning telefon raqamini kiriting:\nMasalan: +998901234567',reply_markup=kb([('Orqaga','q:home')]))
        item = await self.db.invite(mid)
        if flow['stage']=='media':
            await self.send(uid,'<b>Rasm yoki video yuboring</b>\nVideo: 1 daqiqagacha, 20 MB gacha. Media qo‘shish ixtiyoriy.',
                reply_markup=kb([('Rasm/videosiz davom etish',f'q:skip:{mid}')]))
        elif flow['stage']=='title':
            await self.send(uid,f'<b>Ism kiriting:</b>\n{esc(item["title"])}\n\nBoshqa ism yoki qo‘shimcha matn yozishingiz mumkin.',
                reply_markup=kb([('Shu ismni qoldirish',f'q:name:{mid}')]))
        elif flow['stage']=='description':
            await self.send(uid,'<b>Tavsif yuboring:</b>\nTaklifingiz matnini yozing.')
        elif flow['stage']=='preview':
            await self.preview(uid,item)

    async def preview(self, uid, item):
        kind, file_id = item['media_kind'], item['file_id']
        if kind=='photo': await self.call(uid,self.bot.send_photo,photo=file_id)
        elif kind=='video': await self.call(uid,self.bot.send_video,video=file_id)
        elif kind=='video_note': await self.call(uid,self.bot.send_video_note,video_note=file_id)
        rows = []
        if self.cfg.webapp_url: rows.append([self.web_button('Ko‘rinishini ochish',item['id'])])
        rows.append([InlineKeyboardButton(text='🎨 Dizaynni tanlash',callback_data=f'q:design:{item["id"]}')])
        rows.append([InlineKeyboardButton(text='Tasdiqlash',callback_data=f'q:confirm:{item["id"]}'),
                     InlineKeyboardButton(text='Tahrirlash',callback_data=f'q:edit:{item["id"]}')])
        designs={'classic':'Sodda','romantic':'Romantik','playful':'Quvnoq','elegant':'Nafis'}
        await self.send(uid,f'<b>{esc(item["title"])}</b>\n\n{esc(item["description"])}\n\nHa  /  Yo‘q\n\nDizayn: {designs.get(item["design"],"Sodda")}',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    async def show_link(self, uid, item):
        return await self.send(uid,f'<b>Taklif havolasi tayyor</b>\nhttps://t.me/{self.username}?start=i_{item["token"]}\n\n'
            'Havolani bitta oluvchiga yuboring.',reply_markup=kb([('Yangi taklif','q:home' if uid==await self.admin() else 'q:new')]))

    async def deliver_link(self, q, item):
        if not item['link_sent']:
            sent = await self.show_link(q.from_user.id,item)
            if sent:
                await self.db.run('UPDATE q_invites SET link_sent=1 WHERE id=?',(item['id'],))
                try:
                    await self.bot.edit_message_reply_markup(chat_id=q.from_user.id,
                        message_id=q.message.message_id,reply_markup=None)
                except TelegramAPIError:
                    pass

    async def open_invite(self, uid, token):
        mid = await self.db.claim(token,uid)
        if mid is None:
            await self.send(uid,'Bu taklif ishlatilgan yoki muddati tugagan.')
        elif not self.cfg.webapp_url:
            await self.send(uid,'Sahifa hozir ishlamayapti. Keyinroq havolani qayta oching.')
        else:
            await self.send(uid,'Siz uchun taklif bor.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                self.web_button('Taklifni ochish',mid)]]))

    async def message(self, m):
        uid = m.from_user.id
        await self.db.profile(m.from_user)
        user = await self.db.one('SELECT * FROM users WHERE tg_id=?',(uid,))
        if user['is_blocked']: return
        text = (m.text or '').strip()
        cmd = text.split(maxsplit=1)[0].split('@')[0] if text else ''
        if cmd=='/start':
            parts=text.split(maxsplit=1)
            if len(parts)>1 and parts[1].startswith('i_'):
                return await self.open_invite(uid,parts[1][2:])
            if await self.db.one('SELECT uid FROM q_suggestion_drafts WHERE uid=?',(uid,)):
                return await self.send(uid,'Taklifingizni matn ko‘rinishida yuboring. Bekor qilish: /cancel')
            # A spent sender permission must not prevent recovery of a created link.
            unsent=await self.db.one("SELECT * FROM q_invites WHERE sender=? AND status='ready' AND link_sent=0 ORDER BY id DESC LIMIT 1",(uid,))
            if unsent:
                sent=await self.show_link(uid,unsent)
                if sent: await self.db.run('UPDATE q_invites SET link_sent=1 WHERE id=?',(unsent['id'],))
                return
            flow = await self.db.flow(uid)
            if flow and await self.is_sender(uid): return await self.prompt(uid)
            return await self.home(uid)
        if m.contact: return await self.contact(m)
        if cmd=='/admin' and uid==await self.admin(): return await self.home(uid)
        if cmd=='/taklif':
            profile=await self.db.one('SELECT phone_hash FROM q_profiles WHERE uid=?',(uid,))
            if not profile or not profile['phone_hash']:
                return await self.send(uid,'Avval /start orqali ro‘yxatdan o‘ting va telefon raqamingizni tasdiqlang.')
            await self.db.run('INSERT OR IGNORE INTO q_suggestion_drafts VALUES(?)',(uid,))
            return await self.send(uid,'Taklifingizni matn ko‘rinishida yuboring. Bekor qilish: /cancel')
        if cmd=='/cancel' and await self.db.one('SELECT uid FROM q_suggestion_drafts WHERE uid=?',(uid,)):
            await self.db.run('DELETE FROM q_suggestion_drafts WHERE uid=?',(uid,))
            return await self.send(uid,'Taklif yozish bekor qilindi.')
        if await self.db.one('SELECT uid FROM q_suggestion_drafts WHERE uid=?',(uid,)):
            if not text or cmd.startswith('/') or len(text)>2000:
                return await self.send(uid,'Taklifni 1–2000 belgili matn sifatida yuboring.')
            async with self.db.connect(True) as connection:
                result=await connection.execute('INSERT INTO q_suggestions(uid,body,created_at) VALUES(?,?,?)',(uid,text,time.time()))
                suggestion_id=result.lastrowid
                await connection.execute('DELETE FROM q_suggestion_drafts WHERE uid=?',(uid,))
            await self.notify_suggestion(suggestion_id)
            suggestion=await self.db.one('SELECT admin_notified FROM q_suggestions WHERE id=?',(suggestion_id,))
            return await self.send(uid,'Taklifingiz adminga yuborildi.' if suggestion['admin_notified'] else 'Taklifingiz saqlandi; adminga qayta yuboriladi.')
        if cmd=='/cancel' and await self.is_sender(uid):
            await self.db.run('DELETE FROM q_flows WHERE uid=?',(uid,))
            await self.db.run("DELETE FROM q_invites WHERE sender=? AND status='draft'",(uid,))
            return await self.home(uid)
        if not await self.is_sender(uid): return
        flow = await self.db.flow(uid)
        if not flow: return await self.home(uid)
        if flow['stage']=='phone': return await self.choose_phone(uid,text)
        item = await self.db.invite(flow['invite_id'])
        if not item or item['status']!='draft': return await self.home(uid)
        if flow['stage']=='media':
            media, kind = (select_photo(m.photo), 'photo') if m.photo else (m.video,'video') if m.video else (m.video_note,'video_note') if m.video_note else (None,None)
            if not media:
                return await self.prompt(uid)
            if kind!='photo' and media.duration>60:
                return await self.send(uid,'Video 1 daqiqadan oshmasin. Qisqaroq video yuboring.')
            if kind=='video' and m.video.mime_type not in (None,'video/mp4'):
                return await self.send(uid,'Videoni MP4 formatida yuboring.')
            size=media.file_size
            if size is None:
                size=(await self.bot.get_file(media.file_id)).file_size
            if size is None or size>MAX_MEDIA:
                return await self.send(uid,'Fayl 20 MB dan oshmasin. Kichikroq fayl yuboring.')
            await self.db.run('UPDATE q_invites SET media_kind=?,file_id=? WHERE id=?',(kind,media.file_id,item['id']))
            await self.db.stage(uid,'title',item['id'])
            return await self.prompt(uid)
        if flow['stage'] in ('title','description'):
            limit=120 if flow['stage']=='title' else 2000
            if not text or cmd.startswith('/') or len(text)>limit:
                return await self.send(uid,f'Matn 1–{limit} belgidan iborat bo‘lsin.')
            column=flow['stage']
            await self.db.run(f'UPDATE q_invites SET {column}=? WHERE id=?',(text,item['id']))
            await self.db.stage(uid,'description' if column=='title' else 'preview',item['id'])
            return await self.prompt(uid)
        return await self.prompt(uid)

    async def callback(self, q):
        uid=q.from_user.id
        await self.db.profile(q.from_user)
        await self.bot.answer_callback_query(q.id)
        user=await self.db.one('SELECT is_blocked FROM users WHERE tg_id=?',(uid,))
        if user['is_blocked']: return
        parts=(q.data or '').split(':')
        if len(parts)<2 or parts[0]!='q': return  # Old menus have no active handlers.
        action=parts[1]
        if action=='request': return await self.request_sender(uid)
        if action=='quota' and len(parts)==3 and parts[2] in ('1','10','30'):
            row=await self.db.sender_request(uid,int(parts[2]))
            if row:
                await self.notify_sender_request(row['id'])
                notified=await self.db.one('SELECT admin_notified FROM q_sender_requests WHERE id=?',(row['id'],))
                text='So‘rovingiz adminga yuborildi. Admin tasdiqlasa, ishni boshlaymiz.' if notified['admin_notified'] else 'So‘rovingiz saqlandi; adminga qayta yuboriladi.'
                return await self.send(uid,text)
            return await self.send(uid,'Avval /start orqali ro‘yxatdan o‘ting yoki avvalgi so‘rovingiz javobini kuting.')
        if action=='later': return await self.send(uid,'Tushunarli. Kerak bo‘lsa /start bosing.')
        if action=='contact': return await self.contact_prompt(uid)
        if action in ('approve','deny','requests','ideas','idea_yes','idea_no'):
            if uid!=await self.admin(): return
            if action=='ideas':
                rows=await self.db.all("SELECT id FROM q_suggestions WHERE status='pending' ORDER BY id LIMIT 20")
                if not rows: return await self.send(uid,'Kutilayotgan takliflar yo‘q.')
                for row in rows: await self.notify_suggestion(row['id'],force=True)
                return
            if action in ('idea_yes','idea_no') and len(parts)==3 and parts[2].isdigit():
                suggestion_id=int(parts[2])
                result=await self.db.decide_suggestion(suggestion_id,uid,action=='idea_yes')
                if result is None: return await self.send(uid,'Taklif avval ko‘rib chiqilgan yoki ruxsat berib bo‘lmaydi.')
                await self.notify_suggestion(suggestion_id)
                await self.send(uid,'Taklif ko‘rib chiqildi.')
                try: await self.bot.edit_message_reply_markup(chat_id=uid,message_id=q.message.message_id,reply_markup=None)
                except TelegramAPIError: pass
                return
            if action=='requests':
                rows=await self.db.all("SELECT id FROM q_sender_requests WHERE status='pending' ORDER BY id LIMIT 20")
                if not rows: return await self.send(uid,'Kutilayotgan sender so‘rovlari yo‘q.')
                for row in rows: await self.notify_sender_request(row['id'],force=True)
                return
            if len(parts)==3 and parts[2].isdigit():
                return await self.decide_sender(q,int(parts[2]),action=='approve')
            return
        if action=='confirm' and len(parts)==3 and parts[2].isdigit():
            item=await self.db.invite(int(parts[2]))
            if item and item['sender']==uid and item['status']!='draft':
                return await self.deliver_link(q,item)
        if action=='new' and not await self.is_sender(uid): return await self.home(uid)
        if not await self.is_sender(uid): return
        if action=='home':
            if uid==await self.admin():
                # Leave an unfinished invitation resumable, but leave phone entry.
                await self.db.run("DELETE FROM q_flows WHERE uid=? AND stage='phone'",(uid,))
            return await self.home(uid)
        if action in ('self','phone'):
            if uid!=await self.admin(): return
            if action=='phone':
                await self.db.stage(uid,'phone')
            else:
                await self.db.run("DELETE FROM q_flows WHERE uid=? AND stage='phone'",(uid,))
                await self.db.begin(uid)
            return await self.prompt(uid)
        if action=='new':
            await self.db.begin(uid)
            return await self.prompt(uid)
        if action=='style' and len(parts)==4 and parts[2].isdigit() and parts[3] in ('classic','romantic','playful','elegant'):
            mid=int(parts[2])
            item=await self.db.invite(mid)
            flow=await self.db.flow(uid)
            if not item or item['sender']!=uid or item['status']!='draft' or not flow or flow['invite_id']!=mid or flow['stage']!='preview': return
            await self.db.run('UPDATE q_invites SET design=? WHERE id=?',(parts[3],mid))
            return await self.preview(uid,await self.db.invite(mid))
        if len(parts)!=3 or not parts[2].isdigit(): return
        mid=int(parts[2])
        item=await self.db.invite(mid)
        if not item or item['sender']!=uid: return
        if action=='confirm' and item['status']!='draft':
            return await self.deliver_link(q,item)
        flow=await self.db.flow(uid)
        if not flow or flow['invite_id']!=mid or item['status']!='draft': return
        if action=='design' and flow['stage']=='preview':
            return await self.send(uid,'<b>Taklif dizaynini tanlang:</b>\nTanlagandan so‘ng ko‘rinishini ochib tekshirishingiz mumkin.',reply_markup=kb(
                [('🤍 Sodda',f'q:style:{mid}:classic'),('🌸 Romantik',f'q:style:{mid}:romantic')],
                [('🎉 Quvnoq',f'q:style:{mid}:playful'),('✨ Nafis',f'q:style:{mid}:elegant')]))
        if action=='skip' and flow['stage']=='media':
            await self.db.run("UPDATE q_invites SET media_kind='none',file_id='' WHERE id=?",(mid,))
            await self.db.stage(uid,'title',mid)
        elif action=='name' and flow['stage']=='title':
            await self.db.stage(uid,'description',mid)
        elif action=='edit' and flow['stage']=='preview':
            await self.db.stage(uid,'media',mid)
        elif action=='confirm' and flow['stage']=='preview':
            if not self.cfg.webapp_url:
                return await self.send(uid,'HTTPS sahifa ishlamayapti. Botni run.py orqali ishga tushiring, keyin tasdiqlang.')
            item=await self.db.publish(mid,uid,self.cfg.ttl)
            if item: return await self.deliver_link(q,item)
        else: return
        await self.prompt(uid)

    async def guard(self, event, callback=False):
        async with self.lock:
            try:
                if not callback:
                    if not await self.db.run('INSERT OR IGNORE INTO q_seen VALUES(?,?)',(event.from_user.id,event.message_id)):
                        return
                await (self.callback(event) if callback else self.message(event))
            except Exception as exc:
                logging.error('Taklif amali: %s',type(exc).__name__)
                # State persists; /start resumes the current step after delivery errors.
                try:
                    await self.send(event.from_user.id,'Amal tugamadi. Davom etish uchun /start bosing.')
                except TelegramAPIError:
                    pass

def dispatcher(app):
    dp=Dispatcher()
    async def message(m: Message): await app.guard(m)
    async def callback(q: CallbackQuery): await app.guard(q,True)
    dp.message.register(message,F.chat.type=='private')
    dp.callback_query.register(callback,F.message.chat.type=='private')
    return dp

async def main():
    cfg=Config.load()
    if not cfg.webapp_url:
        raise ValueError('HTTPS sahifa kerak. Botni python run.py orqali ishga tushiring.')
    db=InvitationDB(cfg.db_path)
    await db.init()
    bot=Bot(cfg.token,default=DefaultBotProperties(parse_mode='HTML'))
    async with bot:
        me=await bot.get_me()
        app=App(bot,db,cfg,me.username)
        from webapp import start_web_app
        runner=await start_web_app(app)
        notices = asyncio.create_task(app.acceptance_notifications())
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            await bot.set_my_commands([BotCommand(command='start',description='Boshlash yoki davom etish'),BotCommand(command='taklif',description='Taklif yuborish')])
            await bot.delete_webhook(drop_pending_updates=False)
            app.ready=True
            logging.warning('Minimal taklif boti ishga tushdi: @%s',me.username)
            await dispatcher(app).start_polling(bot,handle_as_tasks=False)
        finally:
            app.ready=False
            notices.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await notices
            await runner.cleanup()

if __name__=='__main__':
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    try: asyncio.run(main())
    except (ValueError,TelegramAPIError) as exc:
        print(str(exc) if isinstance(exc,ValueError) else f'Telegram ulanishi: {type(exc).__name__}.')
        raise SystemExit(1)
