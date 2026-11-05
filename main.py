"""Qadam: admin -> sender wizard -> one receiver -> thank you."""
import asyncio
import contextlib
import hashlib
import hmac
import html
import json
import logging
import os
import re
import time
from urllib.parse import urlencode
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo, MenuButtonCommands)
from designs import DESIGNS, valid_design
from config import Config
from invitation_store import InvitationDB, parse_details, valid_ceremony_details, EVENT_KINDS, ceremony_expiry

MAX_MEDIA = 20 * 1024 * 1024
CEREMONY_LABELS = {'wedding':'To‘y', 'nikah':'Nikoh', 'beshik':'Beshik to‘y', 'sunnat':'Sunnat to‘y', 'fotiha':'Fotiha', 'birthday':'Tug‘ilgan kun', 'other':'Boshqa'}
CEREMONY_STAGES = ('c_kind','c_title','c_date','c_time','c_address','c_map','c_program','c_note','c_media','c_layout','c_design','c_share','c_preview')

def select_photo(photos):
    suitable = [photo for photo in photos if photo.width >= 720]
    selected = min(suitable, key=lambda photo: photo.width) if suitable else max(photos, key=lambda photo: photo.width)
    logging.warning('Photo dimensions: %d x %d', selected.width, selected.height)
    return selected

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
        self.photo_cache = None
        self.photo_lock = asyncio.Lock()
        self.ready = False
        self.rsvp_requests = {}

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

    async def notify_rsvp(self, mid, uid=None):
        async with self.notice_lock:
            response=await self.db.one("SELECT rowid AS notice_id,* FROM q_rsvps WHERE invite_id=? AND notice_status='pending' AND (? IS NULL OR telegram_user_id=?) ORDER BY rowid LIMIT 1",(mid,uid,uid))
            if not response: return
            item=await self.db.invite(mid)
            decision='Kelaman' if response['attending'] else 'Kela olmayman'
            text=(f'💌 <b>Taklifga javob</b>\nTaklif #{mid}: {esc(item["title"])}\n'
                  f'Oluvchi: {esc(response["receiver_name"])}\nJavob: {decision}\nMehmonlar soni: {response["guests"]}')
            try: sent=await asyncio.wait_for(self.send(item['sender'],text),timeout=10)
            except (TelegramAPIError,OSError,TimeoutError) as exc:
                logging.warning('RSVP xabari keyinroq yuboriladi: %s',type(exc).__name__)
                return
            await self.db.run('UPDATE q_rsvps SET notice_status=? WHERE rowid=?',('sent' if sent else 'failed',response['notice_id']))

    async def acceptance_notifications(self):
        while True:
            try:
                notices = await self.db.all("SELECT invite_id FROM q_accept_notices WHERE status='pending' ORDER BY invite_id LIMIT 20")
                for notice in notices:
                    await self.notify_acceptance(notice['invite_id'])
                rsvps=await self.db.all("SELECT invite_id,telegram_user_id FROM q_rsvps WHERE notice_status='pending' ORDER BY invite_id LIMIT 20")
                for response in rsvps:
                    await self.notify_rsvp(response['invite_id'],response['telegram_user_id'])
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
        if not getattr(self.cfg,'enable_ceremony',False) and item['type']=='ceremony' and item['status']=='draft':
            return await self.send(uid,'Marosim yaratish vaqtincha o‘chirilgan. Qoralama saqlandi; bekor qilish: /cancel.')
        if flow['stage']=='type' and not getattr(self.cfg,'enable_ceremony',False):
            await self.db.stage(uid,'media',mid)
            return await self.prompt(uid)
        if flow['stage']=='type':
            return await self.send(uid,'<b>Taklif turini tanlang:</b>',reply_markup=kb(
                [('🎈 Ko‘ngilochar',f'q:ctype:{mid}:fun'),('💍 To‘y va marosimlar',f'q:ctype:{mid}:ceremony')],
                [('Orqaga',f'q:leave:{mid}'),('Bekor qilish',f'q:ccancel:{mid}')]))
        if flow['stage'].startswith('c_'):
            return await self.ceremony_prompt(uid,item,flow['stage'])
        if flow['stage']=='media':
            await self.send(uid,'<b>Rasm yoki video yuboring</b>\nVideo: 1 daqiqagacha, 20 MB gacha. Media qo‘shish ixtiyoriy.',
                reply_markup=kb([('Rasm/videosiz davom etish',f'q:skip:{mid}')]))
        elif flow['stage']=='title':
            await self.send(uid,f'<b>Ism kiriting:</b>\n{esc(item["title"])}\n\nBoshqa ism yoki qo‘shimcha matn yozishingiz mumkin.',
                reply_markup=kb([('Shu ismni qoldirish',f'q:name:{mid}')]))
        elif flow['stage']=='description':
            await self.send(uid,'<b>Tavsif yuboring:</b>\nTaklifingiz matnini yozing.')
        elif flow['stage']=='layout':
            await self.send(uid,'<b>Matn qayerda joylashsin?</b>', reply_markup=kb(
                [('Yuqorida',f'q:layout:{mid}:top'),('O‘rtada',f'q:layout:{mid}:center')],
                [('Pastda',f'q:layout:{mid}:bottom'),('O‘tkazib yuborish',f'q:layout:{mid}:bottom')]))
        elif flow['stage']=='preview':
            await self.preview(uid,item)

    async def preview(self, uid, item):
        kind, file_id = item['media_kind'], item['file_id']
        if kind=='photo': await self.call(uid,self.bot.send_photo,photo=file_id)
        elif kind=='video': await self.call(uid,self.bot.send_video,video=file_id)
        elif kind=='video_note': await self.call(uid,self.bot.send_video_note,video_note=file_id)
        if item['type']=='ceremony':
            details=parse_details(item['details']) or {}
            program='\n'.join('• '+esc(line) for line in details.get('program',[])) or '—'
            text=(f'<b>{esc(item["title"])}</b>\nMarosim: {esc(CEREMONY_LABELS.get(details.get("event_kind"),"—"))}'
                  f'\nSana: {esc(details.get("date","—"))}\nVaqt: {esc(details.get("time","—"))}'
                  f'\nManzil: {esc(details.get("address","—"))}\nXarita: {esc(details.get("map_url") or "—")}'
                  f'\nDastur:\n{program}\nQo‘shimcha matn: {esc(details.get("note","—"))}'
                  f'\nMedia: {esc(kind)}\nMatn joyi: {esc(details.get("layout",{}).get("text_position","bottom"))}'
                  f'\nDizayn: {esc(DESIGNS.get(item["design"],{}).get("label_uz","—"))}'
                  f'\nHavola amal qilish muddati: {datetime.fromtimestamp(ceremony_expiry(details),ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M")} (Toshkent)')
            rows=[]
            if self.cfg.webapp_url: rows.append([self.web_button('Ko‘rinishini ochish',item['id'])])
            rows.append([InlineKeyboardButton(text='Tasdiqlash',callback_data=f'q:confirm:{item["id"]}')])
            rows.append([InlineKeyboardButton(text='Orqaga',callback_data=f'q:cback:{item["id"]}'),InlineKeyboardButton(text='Bekor qilish',callback_data=f'q:ccancel:{item["id"]}')])
            return await self.send(uid,text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        rows = []
        if self.cfg.webapp_url: rows.append([self.web_button('Ko‘rinishini ochish',item['id'])])
        rows.append([InlineKeyboardButton(text='🎨 Dizaynni tanlash',callback_data=f'q:design:{item["id"]}')])
        rows.append([InlineKeyboardButton(text='Tasdiqlash',callback_data=f'q:confirm:{item["id"]}'),
                     InlineKeyboardButton(text='Tahrirlash',callback_data=f'q:edit:{item["id"]}')])
        await self.send(uid,f'<b>{esc(item["title"])}</b>\n\n{esc(item["description"])}\n\nHa  /  Yo‘q\n\nDizayn: {DESIGNS.get(item["design"], DESIGNS["classic"])["label_uz"]}',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    async def ceremony_prompt(self,uid,item,stage):
        mid=item['id']
        labels={'c_title':'Sarlavha yoki ismlarni kiriting (1–120 belgi).', 'c_date':'Sanani DD.MM.YYYY formatida kiriting.',
                'c_time':'Vaqtni HH:MM formatida kiriting.', 'c_address':'Manzilni kiriting (1–300 belgi).',
                'c_map':'Xarita HTTPS havolasini yuboring yoki o‘tkazib yuboring.', 'c_program':'Dasturni har bandni alohida qatorda yuboring yoki o‘tkazib yuboring.',
                'c_note':'Qo‘shimcha matnni kiriting (1–500 belgi).', 'c_media':'Rasm yoki 60 soniyagacha video yuboring yoki o‘tkazib yuboring.',
                'c_layout':'Matn qayerda joylashsin?', 'c_design':'Dizaynni tanlang.', 'c_share':'Havola rejimini tanlang. Ochiq havolani olgan har kim manzil va vaqtni ko‘radi.'}
        rows=[]
        if stage=='c_kind':
            choices=[(label,f'q:cevent:{mid}:{key}') for key,label in CEREMONY_LABELS.items()]
            rows.extend(choices[i:i+2] for i in range(0,len(choices),2))
        elif stage=='c_layout': rows.extend([[('Yuqorida',f'q:clayout:{mid}:top'),('O‘rtada',f'q:clayout:{mid}:center')],[('Pastda',f'q:clayout:{mid}:bottom'),('O‘tkazib yuborish',f'q:clayout:{mid}:bottom')]])
        elif stage=='c_design':
            choices=[(f"{d['emoji']} {d['label_uz']}",f"q:cdesign:{mid}:{d['id']}") for d in DESIGNS.values() if d['type']=='ceremony']
            rows.extend(choices[i:i+2] for i in range(0,len(choices),2))
        elif stage=='c_share': rows.extend([[('🌐 Ochiq havola (standart)',f'q:cshare:{mid}:open')],[('🔒 Shaxsiy havola',f'q:cshare:{mid}:single')]])
        elif stage=='c_preview': return await self.preview(uid,item)
        if stage in ('c_map','c_program','c_media'): rows.append([('O‘tkazib yuborish',f'q:cskip:{mid}')])
        rows.append([('Orqaga',f'q:cback:{mid}'),('Bekor qilish',f'q:ccancel:{mid}')])
        await self.send(uid,'<b>Marosim turini tanlang:</b>' if stage=='c_kind' else esc(labels[stage]),reply_markup=kb(*rows))

    async def cancel_draft(self,uid):
        async with self.photo_lock:
            drafts=await self.db.all("SELECT file_id FROM q_invites WHERE sender=? AND status='draft' AND media_kind='photo'",(uid,))
            await self.db.run('DELETE FROM q_flows WHERE uid=?',(uid,))
            await self.db.run("DELETE FROM q_invites WHERE sender=? AND status='draft'",(uid,))
            if self.photo_cache:
                for draft in drafts: self.photo_cache.remove(draft['file_id'])
        if uid==await self.admin(): return await self.home(uid)
        return await self.send(uid,'Qoralama bekor qilindi.',reply_markup=kb([('Yangi taklif','q:new')]))

    async def show_link(self, uid, item):
        link=f'https://t.me/{self.username}?start=i_{item["token"]}'
        rows=[]
        if item['share_mode']=='open':
            rows.append([InlineKeyboardButton(text='Telegram orqali ulashish',url='https://t.me/share/url?'+urlencode({'url':link}))])
            text='Havolani ko‘p mehmonga yuborishingiz mumkin. /guests orqali javoblarni ko‘ring.'
        else: text='Havolani bitta oluvchiga yuboring.'
        rows.append([InlineKeyboardButton(text='Yangi taklif',callback_data='q:home' if uid==await self.admin() else 'q:new')])
        return await self.send(uid,f'<b>Taklif havolasi tayyor</b>\n{link}\n\n{text}',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    async def guests(self, uid, mid=None, page=0):
        if mid is None:
            items=await self.db.all("SELECT id,title FROM q_invites WHERE sender=? AND type='ceremony' AND status!='draft' ORDER BY id DESC",(uid,))
            if not items: return await self.send(uid,'Marosim takliflari topilmadi.')
            if len(items)==1: return await self.guests(uid,items[0]['id'])
            # Limit each selection page so Telegram message and keyboard limits are respected.
            page=max(0,page); chunk=items[page*15:(page+1)*15]
            rows=[[(f"#{x['id']} {x['title'][:45]}",f"q:guests:{x['id']}:0")] for x in chunk]
            nav=[]
            if page: nav.append(('⬅️',f'q:glist:{page-1}'))
            if (page+1)*15<len(items): nav.append(('➡️',f'q:glist:{page+1}'))
            if nav: rows.append(nav)
            return await self.send(uid,'Taklifni tanlang:',reply_markup=kb(*rows))
        item=await self.db.one("SELECT * FROM q_invites WHERE id=? AND sender=? AND type='ceremony' AND status!='draft'",(mid,uid))
        if not item: return await self.send(uid,'Taklif topilmadi.')
        stats=await self.db.one('SELECT COALESCE(SUM(attending),0) yes,COALESCE(SUM(CASE WHEN attending=1 THEN guests ELSE 0 END),0) total,COALESCE(SUM(CASE WHEN attending=0 THEN 1 ELSE 0 END),0) no FROM q_rsvps WHERE invite_id=?',(mid,))
        responses=await self.db.all('SELECT receiver_name,attending,guests FROM q_rsvps WHERE invite_id=? ORDER BY responded_at,rowid LIMIT 2 OFFSET ?',(mid,max(0,page)*2))
        lines=[f"{esc(x['receiver_name'])}: {'Kelaman' if x['attending'] else 'Kela olmayman'} — {x['guests']} kishi" for x in responses]
        text=f"<b>{esc(item['title'])}</b>\nKelaman: {stats['yes']} (jami {stats['total']} kishi)\nKela olmayman: {stats['no']}\n\n"+'\n'.join(lines)
        nav=[]
        if page>0: nav.append(('⬅️',f'q:guests:{mid}:{page-1}'))
        if (page+1)*2 < stats['yes']+stats['no']: nav.append(('➡️',f'q:guests:{mid}:{page+1}'))
        return await self.send(uid,text,reply_markup=kb(nav) if nav else None)

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
        if cmd=='/guests': return await self.guests(uid)
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
            return await self.cancel_draft(uid)
        if not await self.is_sender(uid): return
        flow = await self.db.flow(uid)
        if not flow: return await self.home(uid)
        if flow['stage']=='phone': return await self.choose_phone(uid,text)
        item = await self.db.invite(flow['invite_id'])
        if not item or item['status']!='draft': return await self.home(uid)
        stage=flow['stage']
        if item['type']=='ceremony' and not getattr(self.cfg,'enable_ceremony',False): return await self.prompt(uid)
        if item['type']=='ceremony' and stage in ('c_title','c_date','c_time','c_address','c_map','c_program','c_note'):
            if not text or cmd.startswith('/'):
                return await self.send(uid,'Ma’lumotni matn ko‘rinishida yuboring.')
            if stage=='c_title':
                if len(text)>120: return await self.send(uid,'Sarlavha 1–120 belgidan iborat bo‘lsin.')
                await self.db.run('UPDATE q_invites SET title=? WHERE id=?',(text,item['id']))
            else:
                field={'c_date':'date','c_time':'time','c_address':'address','c_map':'map_url','c_program':'program','c_note':'note'}[stage]
                value=[line.strip() for line in text.splitlines() if line.strip()] if stage=='c_program' else text
                if not await self.db.update_ceremony_details(item['id'],uid,{field:value}):
                    return await self.send(uid,'Ma’lumot noto‘g‘ri yoki belgilangan chegaradan oshgan. Qayta kiriting.')
                if stage=='c_note': await self.db.run('UPDATE q_invites SET description=? WHERE id=?',(text,item['id']))
            await self.db.stage(uid,CEREMONY_STAGES[CEREMONY_STAGES.index(stage)+1],item['id'])
            return await self.prompt(uid)
        if stage in ('media','c_media'):
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
            await self.db.stage(uid,'c_layout' if stage=='c_media' else 'title',item['id'])
            return await self.prompt(uid)
        if flow['stage'] in ('title','description'):
            limit=120 if flow['stage']=='title' else 2000
            if not text or cmd.startswith('/') or len(text)>limit:
                return await self.send(uid,f'Matn 1–{limit} belgidan iborat bo‘lsin.')
            column=flow['stage']
            await self.db.run(f'UPDATE q_invites SET {column}=? WHERE id=?',(text,item['id']))
            await self.db.stage(uid,'description' if column=='title' else 'layout',item['id'])
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
        if not getattr(self.cfg,'enable_ceremony',False):
            if (action=='ctype' and len(parts)==4 and parts[3]=='ceremony') or action in ('cevent','clayout','cdesign','cshare','cback','cskip'):
                return await self.send(uid,'Marosim yaratish vaqtincha o‘chirilgan.')
            if action=='confirm' and len(parts)==3 and parts[2].isdigit():
                draft=await self.db.invite(int(parts[2]))
                if draft and draft['sender']==uid and draft['type']=='ceremony' and draft['status']=='draft':
                    return await self.send(uid,'Marosim yaratish vaqtincha o‘chirilgan.')
        if action=='guests' and len(parts)==4 and parts[2].isdigit() and parts[3].isdigit(): return await self.guests(uid,int(parts[2]),int(parts[3]))
        if action=='glist' and len(parts)==3 and parts[2].isdigit(): return await self.guests(uid,page=int(parts[2]))
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
        if action in ('ctype','cevent','clayout','cdesign','cshare') and len(parts)==4 and parts[2].isdigit():
            mid=int(parts[2]); item=await self.db.invite(mid); flow=await self.db.flow(uid)
            if not item or item['sender']!=uid or item['status']!='draft' or not flow or flow['invite_id']!=mid: return
            choice=parts[3]
            if action=='ctype' and flow['stage']=='type' and choice in ('fun','ceremony'):
                if item['type']!=choice:
                    await self.db.run('UPDATE q_invites SET type=?,design=?,details=?,description=?,share_mode=? WHERE id=?',
                        (choice,'nafis' if choice=='ceremony' else 'classic','{}','', 'open' if choice=='ceremony' else 'single',mid))
                elif choice=='ceremony' and not valid_design(item['design'],'ceremony'):
                    await self.db.run("UPDATE q_invites SET design='nafis' WHERE id=?",(mid,))
                await self.db.stage(uid,'c_kind' if choice=='ceremony' else 'media',mid)
            elif item['type']=='ceremony' and action=='cevent' and flow['stage']=='c_kind' and choice in EVENT_KINDS:
                if not await self.db.update_ceremony_details(mid,uid,{'event_kind':choice}): return
                await self.db.stage(uid,'c_title',mid)
            elif item['type']=='ceremony' and action=='clayout' and flow['stage']=='c_layout' and choice in ('top','center','bottom'):
                if not await self.db.update_ceremony_details(mid,uid,{'layout':{'text_position':choice}}): return
                await self.db.stage(uid,'c_design',mid)
            elif item['type']=='ceremony' and action=='cdesign' and flow['stage']=='c_design' and valid_design(choice,'ceremony'):
                await self.db.run('UPDATE q_invites SET design=? WHERE id=?',(choice,mid))
                await self.db.stage(uid,'c_share',mid)
            elif item['type']=='ceremony' and action=='cshare' and flow['stage']=='c_share' and choice in ('open','single'):
                await self.db.run('UPDATE q_invites SET share_mode=? WHERE id=?',(choice,mid))
                await self.db.stage(uid,'c_preview',mid)
            else: return
            return await self.prompt(uid)
        if action in ('cback','cskip','ccancel','leave') and len(parts)==3 and parts[2].isdigit():
            mid=int(parts[2]); item=await self.db.invite(mid); flow=await self.db.flow(uid)
            if not item or item['sender']!=uid or item['status']!='draft' or not flow or flow['invite_id']!=mid: return
            if action=='ccancel': return await self.cancel_draft(uid)
            if action=='leave' and flow['stage']=='type':
                if uid==await self.admin(): return await self.home(uid)
                return await self.send(uid,'Qoralama saqlandi. Davom etish uchun /start bosing.')
            if item['type']!='ceremony' or flow['stage'] not in CEREMONY_STAGES: return
            stage=flow['stage']
            if action=='cback':
                index=CEREMONY_STAGES.index(stage)
                await self.db.stage(uid,CEREMONY_STAGES[index-1] if index else 'type',mid)
            elif action=='cskip' and stage in ('c_map','c_program','c_media'):
                if stage=='c_media': await self.db.run("UPDATE q_invites SET media_kind='none',file_id='' WHERE id=?",(mid,))
                else: await self.db.update_ceremony_details(mid,uid,{'map_url':''} if stage=='c_map' else {'program':[]})
                await self.db.stage(uid,CEREMONY_STAGES[CEREMONY_STAGES.index(stage)+1],mid)
            else: return
            return await self.prompt(uid)
        if action=='layout' and len(parts)==4 and parts[2].isdigit():
            mid=int(parts[2])
            item=await self.db.invite(mid)
            flow=await self.db.flow(uid)
            if not item or item['sender']!=uid or item['status']!='draft' or not flow or flow['invite_id']!=mid or flow['stage']!='layout': return
            if parts[3] not in ('top','center','bottom'): return
            details=parse_details(item['details'])
            if details is None: return await self.send(uid,'Taklif ma’lumotlari noto‘g‘ri.')
            details['layout']={**details.get('layout',{}), 'text_position':parts[3]}
            await self.db.run('UPDATE q_invites SET details=? WHERE id=?',(json.dumps(details,ensure_ascii=False),mid))
            await self.db.stage(uid,'preview',mid)
            return await self.preview(uid,await self.db.invite(mid))
        if action=='style' and len(parts)==4 and parts[2].isdigit():
            mid=int(parts[2])
            item=await self.db.invite(mid)
            flow=await self.db.flow(uid)
            if not item or item['sender']!=uid or item['status']!='draft' or not flow or flow['invite_id']!=mid or flow['stage']!='preview' or not valid_design(parts[3], item['type']): return
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
            choices = [(f"{d['emoji']} {d['label_uz']}", f"q:style:{mid}:{d['id']}")
                       for d in DESIGNS.values() if d['type']==item['type']]
            return await self.send(uid,'<b>Taklif dizaynini tanlang:</b>\nTanlagandan so‘ng ko‘rinishini ochib tekshirishingiz mumkin.',reply_markup=kb(
                *(choices[i:i+2] for i in range(0,len(choices),2))))
        if action=='skip' and flow['stage']=='media':
            await self.db.run("UPDATE q_invites SET media_kind='none',file_id='' WHERE id=?",(mid,))
            await self.db.stage(uid,'title',mid)
        elif action=='name' and flow['stage']=='title':
            await self.db.stage(uid,'description',mid)
        elif action=='edit' and flow['stage']=='preview':
            await self.db.stage(uid,'media',mid)
        elif action=='confirm' and flow['stage'] in ('preview','c_preview'):
            if not self.cfg.webapp_url:
                return await self.send(uid,'HTTPS sahifa ishlamayapti. Botni run.py orqali ishga tushiring, keyin tasdiqlang.')
            item=await self.db.publish(mid,uid,self.cfg.ttl)
            if item: return await self.deliver_link(q,item)
            return await self.send(uid,'Taklif ma’lumotlari noto‘g‘ri yoki sana o‘tgan. Orqaga qaytib tekshiring.')
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
    env_file=os.getenv('CONFIG_ENV_FILE')
    cfg=Config.load(env_file) if env_file else Config.load()
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
            await bot.set_my_commands([BotCommand(command='start',description='Boshlash yoki davom etish'),BotCommand(command='taklif',description='Taklif yuborish'),BotCommand(command='guests',description='Mehmonlar ro‘yxati')])
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
