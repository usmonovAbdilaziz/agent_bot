"""Rasm ulashish va rozilik asosidagi suhbat boti. Python 3.11+."""
import asyncio
import contextlib
import html
import logging
import os
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (BotCommand, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    WebAppInfo, MenuButtonWebApp)
from dotenv import load_dotenv

from db import DB

ROOT = Path(__file__).resolve().parent
NOTICE = "Suhbat ochildi. Xabarlar bot orqali o'tadi va admin nazorat qilishi mumkin. Admin faqat o'z suhbatlari va shikoyat qilingan xabarlarni ko'radi. Yopish: /yopish"
HELP = ("👥 <b>Sender va receiver</b>\nSender — rasm yuboruvchi, receiver — rasmni oluvchi. Ularni alohida yaratish shart emas. Har kim, jumladan admin, rasm yuborishi mumkin.\n\n"
        "📷 <b>Rasm yuborish</b>\nRasm jo'nating, oluvchini tanlang yoki bir martalik havola yarating. Oluvchi rozilik bildirgach suhbat ochiladi.\n\n"
        "💬 <b>Suhbat</b>\nMatn, rasm va ovozli xabar yuborishingiz mumkin. Bir nechta suhbatda kerakli xabarga Reply qiling.\n\n"
        "/yangi — yangi rasm yuborish\n/kirishlar — kelgan rasmlar\n/mening — rasmlarim va havolalarim\n/sessions — suhbatlar\n/yopish — suhbatni yopish\n/bloklash — suhbatdoshni bloklash\n/bloklar — shaxsiy bloklar\n/stop — xabar olishni to'xtatish\n/start — qayta yoqish\n/help — yordam\n\n"
        "Ismingiz oluvchiga ko'rinadi. Suhbat matnlari bazaga yozilmaydi. Boshlang'ich rasm izohi va Telegram file_id bazada saqlanadi.")


def esc(value):
    return html.escape(str(value or ''))


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t, callback_data=d) for t,d in row] for row in rows])


def controls(sid):
    return kb([('🚩 Shikoyat',f'report:{sid}'),('🚫 Bloklash',f'block:{sid}')], [('✖️ Yopish',f'close:{sid}')])


@dataclass
class Config:
    token: str
    admin_phone: str
    moderation: bool = True
    ttl: float = 48 * 3600
    idle: float = 24 * 3600
    db_path: str = str(ROOT / 'data/bot.sqlite3')
    webapp_url: str = ''
    webapp_port: int = 8080

    @classmethod
    def load(cls):
        load_dotenv(ROOT / '.env')
        token = os.getenv('BOT_TOKEN','').strip()
        phone = re.sub(r'\D','',os.getenv('ADMIN_PHONE',''))
        if not token or not phone:
            raise ValueError(".env faylida BOT_TOKEN va ADMIN_PHONE ni to'ldiring.")
        mode = os.getenv('MODERATION','on').lower()
        if mode not in ('on','off'):
            raise ValueError('MODERATION on yoki off bo‘lishi kerak.')
        ttl = float(os.getenv('LINK_TTL_HOURS','48')) * 3600
        idle = float(os.getenv('SESSION_IDLE_HOURS','24')) * 3600
        if ttl <= 0 or idle <= 0:
            raise ValueError('Muddatlar musbat son bo‘lishi kerak.')
        path = Path(os.getenv('DB_PATH','data/bot.sqlite3'))
        webapp_url = os.getenv('WEBAPP_URL','').strip().rstrip('/')
        if webapp_url:
            parsed = urlsplit(webapp_url)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
                raise ValueError('WEBAPP_URL ochiq HTTPS manzil bo‘lishi kerak, query va fragment qo‘shmang.')
        port = int(os.getenv('WEBAPP_PORT','8080'))
        if not 1 <= port <= 65535:
            raise ValueError('WEBAPP_PORT 1–65535 oralig‘ida bo‘lsin.')
        return cls(token,phone,mode=='on',ttl,idle,str(path if path.is_absolute() else ROOT/path),webapp_url,port)


class App:
    def __init__(self, bot, db, cfg, username):
        self.bot, self.db, self.cfg, self.username = bot, db, cfg, username
        # Telegram callbacklari va yopish/bloklash/relay bir-birini quvib o'tmaydi.
        self.lock = asyncio.Lock()
        self.unavailable_queue = deque()
        self.handling_unavailable = False

    async def admin(self):
        value = await self.db.setting('admin')
        return int(value) if value else None

    def web_button(self, label, **query):
        url = self.cfg.webapp_url + '/'
        if query:
            url += '?' + urlencode(query)
        return InlineKeyboardButton(text=label,web_app=WebAppInfo(url=url))

    async def send(self, uid, text, force=False, **kwargs):
        return await self.call(uid, self.bot.send_message, force=force, text=text, **kwargs)

    async def call(self, uid, method, force=False, **kwargs):
        # Matn, rasm, nusxa va tahrir uchun yagona /stop va blok tekshiruvi.
        if not force:
            u = await self.db.one('SELECT active,is_blocked FROM users WHERE tg_id=?',(uid,))
            if u and (not u['active'] or u['is_blocked']):
                return None
        for attempt in range(2):
            try:
                return await method(chat_id=uid, **kwargs)
            except TelegramRetryAfter as e:
                if attempt or e.retry_after > 3:
                    raise
                await asyncio.sleep(e.retry_after)
            except TelegramForbiddenError:
                await self.unavailable(uid)
                return None

    async def quiet(self, uid, text):
        if uid:
            try:
                await self.send(uid, text)
            except TelegramAPIError:
                pass

    async def unavailable(self, uid):
        # Bir bildirishnomaning o'zi ham 403 qaytarishi mumkin. Rekursiya o'rniga
        # navbat ishlatamiz: har foydalanuvchi shu siklda faqat bir marta yopiladi.
        self.unavailable_queue.append(uid)
        if self.handling_unavailable:
            return
        self.handling_unavailable = True
        seen = set()
        try:
            while self.unavailable_queue:
                current = self.unavailable_queue.popleft()
                if current in seen:
                    continue
                seen.add(current)
                await self.db.run('UPDATE users SET active=0 WHERE tg_id=?',(current,))
                sessions = await self.db.active_sessions(current)
                for s in sessions:
                    await self.db.run("UPDATE sessions SET status='closed' WHERE id=?",(s['id'],))
                    await self.quiet(self.other(s,current),f"Suhbat #{s['id']} yopildi: suhbatdosh botni to'xtatgan.")
                await self.db.log(current,'bot_toxtatildi')
                admin = await self.admin()
                if admin != current:
                    await self.quiet(admin,f"Foydalanuvchi {current} botni to'xtatgan. Uning suhbatlari yopildi.")
        finally:
            self.handling_unavailable = False

    @staticmethod
    def other(s, uid):
        return s['party_b'] if s['party_a'] == uid else s['party_a']

    async def close(self, sid, actor=None):
        s = await self.db.one('SELECT * FROM sessions WHERE id=?',(sid,))
        if not s or not await self.db.run("UPDATE sessions SET status='closed' WHERE id=? AND status='open'",(sid,)):
            return
        await self.db.log(actor,'suhbat_yopildi',sid)
        for uid in (s['party_a'],s['party_b']):
            await self.quiet(uid,f'Suhbat #{sid} yopildi.')

    async def block(self, uid, other):
        await self.db.run('INSERT OR IGNORE INTO pair_blocks VALUES(?,?)',(uid,other))
        for s in await self.db.active_sessions(uid):
            if self.other(s,uid) == other:
                await self.close(s['id'],uid)
        await self.db.log(uid,'shaxsiy_blok',other)

    async def announce(self, sid):
        s = await self.db.one('SELECT * FROM sessions WHERE id=?',(sid,))
        if not s or s['status'] != 'open':
            return False
        notices = await self.db.all('SELECT * FROM session_notices WHERE session_id=?',(sid,))
        for notice in notices:
            if not await self.db.one("SELECT 1 FROM sessions WHERE id=? AND status='open'",(sid,)):
                return False
            uid = notice['chat_id']
            other = self.other(s,uid)
            u = await self.db.one('SELECT first_name FROM users WHERE tg_id=?',(other,))
            if notice['notice_msg_id'] is None:
                try:
                    msg = await self.send(uid,f"💬 <b>Suhbat #{sid} · {esc(u['first_name'])}</b>\n{NOTICE}",reply_markup=controls(sid))
                    if msg:
                        async with self.db.connect(True) as c:
                            await c.execute('INSERT OR REPLACE INTO relay_map VALUES(?,?,?,?)',(uid,msg.message_id,sid,other))
                            await c.execute('UPDATE session_notices SET notice_msg_id=? WHERE session_id=? AND chat_id=?',(msg.message_id,sid,uid))
                        await self.db.log(uid,'suhbat_xabarnomasi',sid)
                except TelegramAPIError as exc:
                    await self.db.log(uid,'xabarnoma_kutilmoqda',type(exc).__name__)
            if notice['photo_msg_id'] and not notice['controls_sent']:
                try:
                    result = await self.call(uid,self.bot.edit_message_reply_markup,
                        message_id=notice['photo_msg_id'],reply_markup=controls(sid))
                    if result:
                        await self.db.run('UPDATE session_notices SET controls_sent=1 WHERE session_id=? AND chat_id=?',(sid,uid))
                except TelegramAPIError as exc:
                    await self.db.log(uid,'tugmalar_kutilmoqda',type(exc).__name__)
        pending = await self.db.one('SELECT 1 FROM session_notices WHERE session_id=? AND notice_msg_id IS NULL',(sid,))
        opened = await self.db.one("SELECT 1 FROM sessions WHERE id=? AND status='open'",(sid,))
        return bool(opened and not pending and len(notices)==2)

    async def sessions(self, uid, all_sessions=False, page=0):
        rows = await self.db.all("SELECT * FROM sessions WHERE status='open' ORDER BY id DESC") if all_sessions else await self.db.active_sessions(uid)
        if not rows:
            await self.send(uid,'Hozir faol suhbat yo‘q.')
            return
        for s in rows[page*8:page*8+8]:
            await self.announce(s['id'])
            text = f"💬 Suhbat #{s['id']} · {s['party_a']} ↔ {s['party_b']}"
            msg = await self.send(uid,text,reply_markup=kb([('✖️ Yopish',f'close:{s["id"]}')]))
            if msg and uid in (s['party_a'],s['party_b']):
                await self.db.mapping(uid,msg.message_id,s['id'],self.other(s,uid))
        if len(rows) > (page+1)*8:
            await self.send(uid,'Keyingi suhbatlar:',reply_markup=kb([('Keyingi ➡️',f'{"asessions" if all_sessions else "sessions"}:{page+1}')]))

    async def consent(self, mid):
        m = await self.db.one('SELECT * FROM messages WHERE id=?',(mid,))
        if not m or m['status'] != 'approved' or not m['receiver_tg_id']:
            return
        if not await self.db.available(m['sender_tg_id'],m['receiver_tg_id']):
            return
        if self.cfg.webapp_url:
            await self.send(m['receiver_tg_id'],'📩 Sizga rasm yuborildi. Telegram ichidagi sahifada oching.',
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                self.web_button('Rasm sahifasini ochish',message=mid)]]))
            return
        await self.send(m['receiver_tg_id'],'📩 Sizga kimdir rasm yubordi. Ko‘rasizmi?',reply_markup=kb(
            [('👁 Ko‘rish',f'view:{mid}')],[('🚫 Rad etish va bloklash',f'decline:{mid}')]))

    async def publish(self, mid):
        m = await self.db.one('SELECT * FROM messages WHERE id=?',(mid,))
        if m['mode'] == 'direct':
            await self.consent(mid)
            await self.send(m['sender_tg_id'],'✅ Rasm tasdiqlandi. Oluvchining roziligi kutilmoqda. Holat: /mening')
        else:
            token = secrets.token_urlsafe(12)
            await self.db.run('INSERT OR IGNORE INTO links(token,creator_tg_id,message_id,created_at) VALUES(?,?,?,?)',(token,m['sender_tg_id'],mid,time.time()))
            r = await self.db.one('SELECT * FROM links WHERE message_id=?',(mid,))
            await self.show_link(m['sender_tg_id'],r)

    async def show_link(self, uid, r):
        await self.send(uid,f"🔗 <b>Bir martalik havola</b>\nhttps://t.me/{self.username}?start=i_{r['token']}\n\n"
            f"Shu havolani nusxalab, kerakli odamga o'zingiz yuboring. U faqat 1 kishi uchun ishlaydi, yaratilganidan {self.cfg.ttl/3600:g} soat amal qiladi.\nHolat: {self.link_state(r['status'])}",
            reply_markup=kb([('🗑 Havolani bekor qilish',f'revoke:{r["token"]}')]))

    @staticmethod
    def link_state(s):
        return {'new':'yangi','used':'ishlatilgan','revoked':'bekor qilingan','expired':'muddati tugagan'}[s]

    async def link(self, uid, token):
        r = await self.db.one('SELECT * FROM links WHERE token=?',(token,))
        if r and uid != r['creator_tg_id'] and not await self.db.available(uid,r['creator_tg_id']):
            await self.send(uid,'Havola hozir mavjud emas.')
            return
        result,r = await self.db.claim(token,uid,self.cfg.ttl)
        if result == 'invalid':
            await self.send(uid,'Havola yaroqsiz yoki muddati tugagan.')
        elif result == 'own':
            await self.send(uid,'Bu sizning havolangiz.')
        elif result == 'won':
            await self.db.log(uid,'havola_olindi',r['message_id'])
            await self.consent(r['message_id'])
        elif r['claimed_by'] == uid:
            await self.send(uid,'Bu havolani siz ochgansiz. Kelgan rasmlar: /kirishlar')
            await self.consent(r['message_id'])
        else:
            await self.send(uid,'Bu havola allaqachon ishlatilgan. Adminga sender sifatida murojaat qilmoqchimisiz?',reply_markup=kb(
                [('Ha',f'ask:{token}'),('Yo‘q','no')]))

    async def receive_photo(self, m):
        user = await self.db.one('SELECT composing FROM users WHERE tg_id=?',(m.from_user.id,))
        mid = await self.db.draft(m.from_user.id,m.photo[-1].file_id,m.caption or '',m.message_id)
        if mid is None:
            await self.send(m.chat.id,'Bir soatda 10 ta yangi rasm yuborish mumkin. Birozdan keyin urinib ko‘ring.')
            return
        draft = await self.db.one('SELECT * FROM messages WHERE id=?',(mid,))
        if draft['status'] != 'draft':
            await self.send(m.chat.id,'Bu rasm avval qabul qilingan. Holat: /mening')
            return
        await self.db.run('INSERT OR REPLACE INTO message_inputs VALUES(?,?,?,?)',
                         (m.from_user.id,mid,'title',int(bool(user and user['composing']==2))))
        await self.send(m.chat.id,'<b>Rasm sarlavhasi</b>\nRasmga qisqa nom yozing (1–120 belgi).\nBekor qilish: /start')

    async def receive_metadata(self, m, entry):
        uid = m.from_user.id
        draft = await self.db.one("SELECT * FROM messages WHERE id=? AND sender_tg_id=? AND status='draft'",(entry['message_id'],uid))
        if not draft:
            await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
            await self.send(uid,'Bu rasm tanlovi yakunlangan. Yangi rasm: /yangi')
            return
        value = (m.text or '').strip()
        limit = 120 if entry['field']=='title' else 2000
        if not value or len(value)>limit:
            await self.send(uid,f"{'Sarlavha' if entry['field']=='title' else 'Tavsif'}ni matn qilib yozing: 1–{limit} belgi.")
            return
        if entry['field']=='title':
            await self.db.run('UPDATE messages SET title=? WHERE id=?',(value,draft['id']))
            await self.db.run("UPDATE message_inputs SET field='description' WHERE tg_id=?",(uid,))
            await self.send(uid,'<b>Rasm tavsifi</b>\nRasm yonida ko‘rinadigan matnni yozing (1–2000 belgi).\nBekor qilish: /start')
            return
        await self.db.metadata(draft['id'],uid,draft['title'],value)
        await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
        await self.send(uid,f"<b>{esc(draft['title'])}</b>\n{esc(value)}")
        if entry['after_link']:
            await self.sender_callback(uid,['target',str(draft['id']),'0'])
        else:
            await self.choose(uid,draft['id'])

    async def show_metadata(self, uid, m):
        if m.get('title') or m.get('description'):
            await self.send(uid,f"<b>{esc(m['title'])}</b>\n{esc(m['description'])}")

    async def choose(self, uid, mid):
        await self.send(uid,'📷 <b>Rasm tayyor. Kimga yuboramiz?</b>',reply_markup=kb(
            [('👤 Ro‘yxatdan tanlash',f'people:{mid}:0')],
            [('🔗 Bir martalik havola yaratish',f'target:{mid}:0')],[('Bekor',f'cancel:{mid}')]))

    async def review(self, mid):
        m = await self.db.one('SELECT * FROM messages WHERE id=?',(mid,))
        u = await self.db.one('SELECT * FROM users WHERE tg_id=?',(m['sender_tg_id'],))
        admin = await self.admin()
        if admin:
            a = await self.db.one('SELECT active FROM users WHERE tg_id=?',(admin,))
            if a and not a['active']:
                return
            await self.send(admin,f"📥 Tasdiqlash #{mid}\nYuboruvchi: {esc(u['first_name'])} ({u['tg_id']})\nManzil: {m['receiver_tg_id'] or 'bir martalik havola'}")
            await self.show_metadata(admin,m)
            await self.call(admin,self.bot.send_photo,photo=m['file_id'],caption=esc(m['caption']),reply_markup=kb(
                [('✅ Tasdiqlash',f'approve:{mid}'),('❌ Rad etish',f'reject:{mid}')]))

    async def message(self, m: Message):
        uid = m.from_user.id
        cmd = (m.text or '').split(maxsplit=1)[0].split('@')[0] if m.text else ''
        await self.db.register(m.from_user,activate=cmd=='/start')
        user = await self.db.one('SELECT * FROM users WHERE tg_id=?',(uid,))
        if user['is_blocked']:
            await self.send(uid,'Botdan foydalanishingiz cheklangan.',force=True)
            return
        if cmd == '/start':
            await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
            await self.db.run('UPDATE users SET composing=0 WHERE tg_id=?',(uid,))
            if not await self.admin():
                await self.send(uid,'Xush kelibsiz! Admin bo‘lsangiz, o‘z raqamingizni ulashing. Boshqa foydalanuvchilar rasm yuborishlari mumkin.',reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text='📱 Raqamni ulashish',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True))
            else:
                await self.send(uid,'👋 Xush kelibsiz! Rasm yuboring yoki quyidagi menyudan foydalaning.',reply_markup=ReplyKeyboardRemove())
            parts = (m.text or '').split(maxsplit=1)
            if len(parts)>1 and parts[1].startswith('i_'):
                await self.link(uid,parts[1][2:])
            else:
                await self.home(uid)
            await self.recover_pending(uid)
            return
        if not user['active']:
            await self.send(uid,'Xabarlar o‘chirilgan. Qayta yoqish: /start',force=True)
            return
        entry = await self.db.one('SELECT * FROM message_inputs WHERE tg_id=?',(uid,))
        if entry and not cmd.startswith('/') and not m.reply_to_message:
            await self.receive_metadata(m,entry)
            return
        if m.contact:
            admin = await self.admin()
            if admin:
                await self.send(uid,'Admin allaqachon tasdiqlangan.',reply_markup=ReplyKeyboardRemove())
            elif m.contact.user_id != uid or re.sub(r'\D','',m.contact.phone_number) != self.cfg.admin_phone:
                await self.send(uid,'Raqam mos kelmadi. Faqat o‘z kontaktingizni ulashing.')
            else:
                await self.db.run("INSERT OR IGNORE INTO settings VALUES('admin',?)",(str(uid),))
                await self.db.log(uid,'admin_tasdiqlandi')
                await self.send(uid,'✅ Admin tasdiqlandi. Menyu: /admin',reply_markup=ReplyKeyboardRemove())
                await self.flush_reports()
            return
        if cmd == '/help':
            await self.send(uid,HELP)
        elif cmd == '/admin':
            await self.admin_menu(uid)
        elif cmd == '/stop':
            await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
            await self.db.run('UPDATE users SET active=0,composing=0 WHERE tg_id=?',(uid,))
            for s in await self.db.active_sessions(uid):
                await self.close(s['id'],uid)
            await self.send(uid,'Xabar olish to‘xtatildi. Qayta yoqish: /start',force=True)
        elif cmd == '/yangi':
            await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
            await self.db.run('UPDATE users SET composing=1 WHERE tg_id=?',(uid,))
            await self.send(uid,'📷 Bitta rasm va xohlasangiz izoh yuboring.',reply_markup=kb([('Bekor','compose_cancel')]))
        elif cmd == '/sessions':
            await self.sessions(uid)
        elif cmd in ('/yopish','/bloklash'):
            s = await self.db.resolve(uid,m.reply_to_message.message_id if m.reply_to_message else None)
            if not s or s['status'] != 'open':
                await self.send(uid,'Suhbat xabariga Reply qilib buyruqni yuboring yoki /sessions ni oching.')
            elif cmd == '/yopish':
                await self.close(s['id'],uid)
            else:
                await self.block(uid,self.other(s,uid))
                await self.send(uid,'Suhbatdosh bloklandi. Boshqarish: /bloklar')
        elif cmd == '/bloklar':
            await self.blocks(uid)
        elif cmd == '/kirishlar':
            await self.inbox(uid)
        elif cmd == '/mening':
            await self.mine(uid)
        elif cmd.startswith('/'):
            await self.send(uid,'Buyruq topilmadi. Yordam: /help')
        elif user['composing'] and not m.reply_to_message:
            if m.photo:
                await self.receive_photo(m)
            else:
                await self.send(uid,'Yangi yuborish uchun rasm kerak. Bekor qilish:',reply_markup=kb([('Bekor','compose_cancel')]))
        elif m.reply_to_message or await self.db.active_sessions(uid):
            await self.relay(m)
        elif m.photo:
            await self.receive_photo(m)
        else:
            await self.home(uid)

    async def home(self, uid):
        if self.cfg.webapp_url:
            await self.send(uid,'<b>Rasmli sahifa yarating</b>\nRasm, sarlavha va tavsifni Telegram ichidagi sahifada to‘ldiring.',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [self.web_button('Rasmli sahifani ochish')],
                    [InlineKeyboardButton(text='Senderni taklif qilish',callback_data='invite_sender')],
                    [InlineKeyboardButton(text='Suhbatlar',callback_data='sessions:0'),
                     InlineKeyboardButton(text='Yordam',callback_data='help')]]))
            return
        await self.send(uid,'<b>Rasm yuborish va qabul qilish</b>\n'
            'Sender — rasm yuboruvchi. Receiver — bir martalik havolani birinchi ochgan oluvchi. Alohida hisob yaratish kerak emas.\n\n'
            'O‘zingiz rasm yuboring yoki senderni botga taklif qiling. Receiver havolasi rasm yuborilgandan keyin yaratiladi.',reply_markup=kb(
            [('📷 Rasm yuborish','new')],[('🔗 Receiver havolasi yaratish','new_link')],
            [('👤 Senderni taklif qilish','invite_sender')],
            [('📩 Kelgan rasmlar','inbox'),('📤 Mening rasmlarim','mine')],
            [('💬 Suhbatlar','sessions:0'),('❓ Sender / receiver','roles')]))

    async def role_guide(self, uid):
        await self.send(uid,'<b>Sender va receiver qanday yaratiladi?</b>\n\n'
            '<b>1. Sender — yuboruvchi</b>\n'
            'Unga botning kirish havolasini yuboring. U /start bosib, rasm yuboradi. Siz ham sender bo‘la olasiz.\n\n'
            '<b>2. Receiver — oluvchi</b>\n'
            'Sender rasmni yuborib, “Bir martalik havola yaratish”ni tanlaydi va tasdiqlaydi. '
            'Moderatsiya yoqilgan bo‘lsa, avval admin tasdiqlaydi.\n\n'
            '<b>3. Havolani ulashish</b>\n'
            'Bot bergan rasm havolasini oluvchiga yuboring. Uni birinchi ochgan odam receiver bo‘ladi. '
            '“Ko‘rish”ni bossa rasm chiqadi va suhbat ochiladi.\n\n'
            'Oluvchi botda /start bosgan bo‘lsa, uni ro‘yxatdan ham tanlash mumkin.',reply_markup=kb(
                [('👤 Sender uchun kirish havolasi','invite_sender')],
                [('🔗 Receiver uchun rasm havolasi','new_link')]))

    async def invite_sender(self, uid):
        await self.send(uid,f'<b>Senderga yuboriladigan kirish havolasi</b>\nhttps://t.me/{self.username}\n\n'
            'Havolani nusxalab, rasm yuboradigan odamga yuboring. U botda /start → “Rasm yuborish”ni tanlaydi.\n\n'
            'Bu havola botga kirish uchun; bir martalik rasm havolasi keyin, rasm yuborilgach yaratiladi. '
            'Senderga admin huquqi berilmaydi.',reply_markup=kb([('❓ Keyingi qadamlar','roles')]))

    async def inbox(self, uid, page=0):
        rows = await self.db.all("SELECT id FROM messages WHERE receiver_tg_id=? AND status='approved' ORDER BY id DESC LIMIT 9 OFFSET ?",(uid,page*8))
        if not rows:
            await self.send(uid,'Kutilayotgan rasm yo‘q.')
        for r in rows[:8]:
            await self.consent(r['id'])
        if len(rows)>8:
            await self.send(uid,'Davomi:',reply_markup=kb([('Keyingi ➡️',f'inbox:{page+1}')]))

    async def mine(self, uid, page=0):
        rows = await self.db.all('SELECT * FROM messages WHERE sender_tg_id=? ORDER BY id DESC LIMIT 9 OFFSET ?',(uid,page*8))
        states = {'draft':'tanlov kutilmoqda','pending':'admin tasdig‘i kutilmoqda','approved':'tasdiqlangan','rejected':'rad etilgan','delivered':'yetkazilgan'}
        if not rows:
            await self.send(uid,'Hali rasm yubormagansiz. Boshlash: /yangi')
        for m in rows[:8]:
            await self.send(uid,f"📷 Rasm #{m['id']} · {states[m['status']]}")
            if m['status']=='draft':
                await self.choose(uid,m['id'])
            r = await self.db.one('SELECT * FROM links WHERE message_id=?',(m['id'],))
            if r:
                await self.show_link(uid,r)
            elif m['status']=='approved' and m['mode']=='link':
                await self.publish(m['id'])
        if len(rows)>8:
            await self.send(uid,'Davomi:',reply_markup=kb([('Keyingi ➡️',f'mine:{page+1}')]))

    async def blocks(self, uid):
        rows = await self.db.all('SELECT b.blocked,u.first_name FROM pair_blocks b JOIN users u ON u.tg_id=b.blocked WHERE b.blocker=?',(uid,))
        await self.send(uid,'Shaxsiy bloklar. Olib tashlash uchun bosing:' if rows else 'Shaxsiy bloklar yo‘q.')
        for r in rows:
            await self.send(uid,esc(r['first_name']),reply_markup=kb([('Blokdan chiqarish',f'unblock:{r["blocked"]}')]))

    async def relay(self, m):
        uid = m.from_user.id
        s = await self.db.resolve(uid,m.reply_to_message.message_id if m.reply_to_message else None)
        if not s:
            await self.send(uid,'Qaysi suhbatga? Kerakli suhbat xabariga Reply qiling.')
            await self.sessions(uid)
            return
        if s['status']!='open' or s['last_activity']+self.cfg.idle<=time.time():
            await self.close(s['id'])
            await self.send(uid,'Bu suhbat yopilgan. Yangi rasm: /yangi')
            return
        other = self.other(s,uid)
        if not await self.db.available(uid,other):
            await self.close(s['id'])
            return
        # Ikkala tomon ogohlantirishni olmaguncha suhbat matni uzatilmaydi.
        if not await self.announce(s['id']):
            await self.send(uid,'Suhbat xabarnomasi hali yetkazilmadi. Keyinroq qayta yuboring yoki /sessions ni oching.')
            return
        if not (m.text or m.photo or m.voice):
            await self.send(uid,'Suhbatda matn, rasm yoki ovozli xabar yuboring.')
            return
        old = await self.db.one('SELECT 1 FROM relay_map WHERE chat_id=? AND msg_id=?',(uid,m.message_id))
        if old:
            return
        # copyMessage matn oldiga prefiks qo‘sha olmaydi. Alohida nomli sarlavha
        # va unga reply qilingan nusxa matn/caption uzunligini ham saqlaydi.
        header = await self.send(other,f"💬 {esc(m.from_user.first_name)} · #{s['id']}:")
        if not header:
            await self.send(uid,'Xabar yetkazilmadi. Suhbatdosh botni to‘xtatgan.')
            return
        await self.db.mapping(other,header.message_id,s['id'],uid)
        copied = await self.call(other,self.bot.copy_message,from_chat_id=uid,message_id=m.message_id,
            reply_to_message_id=header.message_id,reply_markup=controls(s['id']))
        if copied:
            await self.db.mapping(other,copied.message_id,s['id'],uid)
            await self.db.mapping(uid,m.message_id,s['id'],uid)
            await self.db.run('UPDATE sessions SET last_activity=? WHERE id=?',(time.time(),s['id']))
            await self.db.log(uid,'xabar_uzatildi',s['id'])

    async def callback(self, q: CallbackQuery):
        uid = q.from_user.id
        await q.answer()
        user = await self.db.one('SELECT * FROM users WHERE tg_id=?',(uid,))
        if not user or not user['active'] or user['is_blocked']:
            await self.send(uid,'Bu amal mavjud emas. Qayta boshlash: /start',force=True)
            return
        data = (q.data or '').split(':')
        action = data[0]
        admin = await self.admin()
        admin_actions = {'admin','approve','reject','requests','accept','deny','users','globalblock','moderation','logs','links','asessions','reviews','reports'}
        if action in admin_actions and uid != admin:
            await self.send(uid,'Bu amal faqat admin uchun.')
            return
        if action=='no':
            await self.send(uid,'Bekor qilindi.')
        elif action=='help':
            await self.send(uid,HELP)
        elif action=='roles':
            await self.role_guide(uid)
        elif action=='invite_sender':
            await self.invite_sender(uid)
        elif action in ('new','new_link','compose_cancel'):
            if self.cfg.webapp_url and action in ('new','new_link'):
                await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
                await self.db.run('UPDATE users SET composing=0 WHERE tg_id=?',(uid,))
                await self.send(uid,'Rasm, sarlavha va tavsifni sahifada to‘ldiring.',reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[self.web_button('Rasmli sahifa yaratish',compose=1)]]))
                return
            await self.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
            mode = {'new':1,'new_link':2,'compose_cancel':0}[action]
            await self.db.run('UPDATE users SET composing=? WHERE tg_id=?',(mode,uid))
            text = ('📷 Receiver havolasi uchun avval bitta rasm va xohlasangiz izoh yuboring. '
                    'Keyin havola yaratishni tasdiqlaysiz. Bekor qilish: /start') if action=='new_link' else (
                    '📷 Rasm va xohlasangiz izoh yuboring. Bekor qilish: /start' if action=='new' else 'Bekor qilindi.')
            await self.send(uid,text)
        elif action=='inbox':
            await self.inbox(uid,int(data[1]) if len(data)>1 else 0)
        elif action=='mine':
            await self.mine(uid,int(data[1]) if len(data)>1 else 0)
        elif action in ('sessions','asessions'):
            await self.sessions(uid,action=='asessions',int(data[1]))
        elif action=='unblock':
            await self.db.run('DELETE FROM pair_blocks WHERE blocker=? AND blocked=?',(uid,int(data[1])))
            await self.send(uid,'Shaxsiy blok olib tashlandi.')
        elif action in ('people','target','confirm','cancel'):
            await self.sender_callback(uid,data)
        elif action in ('approve','reject'):
            mid = int(data[1])
            status = 'approved' if action=='approve' else 'rejected'
            if await self.db.run("UPDATE messages SET status=? WHERE id=? AND status='pending'",(status,mid)):
                await self.db.log(uid,'moderatsiya_'+status,mid)
                if action=='approve':
                    await self.publish(mid)
                else:
                    m = await self.db.one('SELECT * FROM messages WHERE id=?',(mid,))
                    await self.send(m['sender_tg_id'],'Xabar yuborilmadi. Admin rad etdi.')
                await self.send(uid,'Qaror saqlandi.')
            else:
                await self.send(uid,'Bu rasm bo‘yicha qaror allaqachon qabul qilingan.')
        elif action in ('view','decline'):
            await self.receiver_callback(uid,int(data[1]),action)
        elif action=='revoke':
            r = await self.db.one('SELECT * FROM links WHERE token=?',(data[1],))
            if r and (r['creator_tg_id']==uid or uid==admin):
                changed = await self.db.run("UPDATE links SET status='revoked' WHERE token=? AND status='new'",(data[1],))
                await self.send(uid,'Havola bekor qilindi.' if changed else 'Havola ishlatilgan yoki allaqachon yopilgan. Suhbatni /sessions orqali yoping.')
                if changed:
                    await self.db.log(uid,'havola_bekor',r['message_id'])
        elif action=='ask':
            if not admin or uid==admin or not await self.db.available(uid,admin):
                await self.send(uid,'Admin hozir murojaat qabul qila olmaydi.')
                return
            rid = await self.db.request_admin(uid,data[1])
            if not rid:
                await self.send(uid,'So‘rov yuborilmadi: 24 soatda bir marta murojaat qilish mumkin yoki havola mos emas.')
                return
            await self.request_card(rid)
            await self.send(uid,'✅ So‘rovingiz adminga yuborildi.')
        elif action in ('accept','deny'):
            rid = int(data[1])
            r = await self.db.one("SELECT * FROM admin_requests WHERE id=? AND status='pending'",(rid,))
            if not r:
                await self.send(uid,'So‘rov allaqachon ko‘rib chiqilgan.')
                return
            if action=='accept' and not await self.db.available(uid,r['tg_id']):
                await self.send(uid,'Bu foydalanuvchi hozir suhbatlasha olmaydi.')
                return
            if action=='accept':
                sid = await self.db.accept_request(rid,uid)
                if sid:
                    await self.announce(sid)
            else:
                await self.db.run("UPDATE admin_requests SET status='rejected' WHERE id=?",(rid,))
                await self.send(r['tg_id'],'So‘rov rad etildi.')
            await self.db.log(uid,'sorov_'+action,rid)
        elif action in ('close','block','report'):
            await self.session_callback(q,int(data[1]),action)
        elif action=='admin':
            await self.admin_menu(uid)
        elif action in ('users','globalblock','moderation','logs','links','requests','reviews','reports'):
            await self.admin_callback(uid,data)

    async def sender_callback(self, uid, data):
        action,mid = data[0],int(data[1])
        m = await self.db.one("SELECT * FROM messages WHERE id=? AND sender_tg_id=? AND status='draft'",(mid,uid))
        if not m:
            await self.send(uid,'Bu tanlov yakunlangan yoki sizga tegishli emas. Holat: /mening')
            return
        if action=='cancel':
            await self.db.run("UPDATE messages SET status='rejected' WHERE id=?",(mid,))
            await self.db.run('DELETE FROM message_inputs WHERE tg_id=? AND message_id=?',(uid,mid))
            await self.send(uid,'Yuborish bekor qilindi.')
        elif action=='people':
            page=max(0,int(data[2]))
            rows = await self.db.all('''SELECT * FROM users u WHERE tg_id!=? AND active=1 AND is_blocked=0
              AND NOT EXISTS(SELECT 1 FROM pair_blocks b WHERE (b.blocker=? AND b.blocked=u.tg_id) OR (b.blocker=u.tg_id AND b.blocked=?))
              ORDER BY first_name,tg_id LIMIT 9 OFFSET ?''',(uid,uid,uid,page*8))
            buttons=[[(r['first_name'][:40]+(f" @{r['username']}" if r['username'] else ''),f'target:{mid}:{r["tg_id"]}')] for r in rows[:8]]
            nav=[]
            if page: nav.append(('⬅️ Oldingi',f'people:{mid}:{page-1}'))
            if len(rows)>8: nav.append(('Keyingi ➡️',f'people:{mid}:{page+1}'))
            if nav: buttons.append(nav)
            buttons.append([('🔗 Havola yaratish',f'target:{mid}:0')])
            await self.send(uid,'Oluvchini tanlang:' if rows else 'Hozir ro‘yxatda mos oluvchi yo‘q.',reply_markup=kb(*buttons))
        elif action=='target':
            target=int(data[2])
            if target and not await self.db.available(uid,target):
                await self.send(uid,'Bu oluvchi hozir mavjud emas.')
                return
            await self.db.run('UPDATE messages SET receiver_tg_id=?,mode=? WHERE id=?',(target or None,'direct' if target else 'link',mid))
            await self.send(uid,"Rasmingiz va ismingiz tanlangan odamga ko'rinadi. Davom etamizmi?",reply_markup=kb([('Ha',f'confirm:{mid}'),('Bekor',f'cancel:{mid}')]))
        elif action=='confirm':
            if not m['title'].strip() or not m['description'].strip():
                field = 'title' if not m['title'].strip() else 'description'
                await self.db.run('INSERT OR REPLACE INTO message_inputs VALUES(?,?,?,?)',
                                 (uid,mid,field,int(m['mode']=='link')))
                await self.send(uid,'Avval rasm sarlavhasini yozing (1–120 belgi).' if field=='title'
                                else 'Avval rasm tavsifini yozing (1–2000 belgi).')
                return
            if not m['mode']:
                return
            if m['receiver_tg_id'] and not await self.db.available(uid,m['receiver_tg_id']):
                await self.send(uid,'Oluvchi hozir mavjud emas.')
                return
            moderated = await self.db.setting('moderation')=='1' and uid!=await self.admin()
            await self.db.run('UPDATE messages SET status=? WHERE id=?',('pending' if moderated else 'approved',mid))
            await self.db.log(uid,'rasm_topshirildi',mid)
            if moderated:
                await self.review(mid)
                await self.send(uid,'⏳ Rasm admin tasdig‘iga yuborildi. Holat: /mening')
            else:
                await self.publish(mid)

    async def receiver_callback(self, uid, mid, action):
        if self.cfg.webapp_url and action=='view':
            owned = await self.db.one('SELECT 1 FROM messages WHERE id=? AND receiver_tg_id=?',(mid,uid))
            if owned:
                await self.send(uid,'Rasmni Telegram ichidagi sahifada ko‘ring.',reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[self.web_button('Rasm sahifasini ochish',message=mid)]]))
            return
        m = await self.db.one("SELECT * FROM messages WHERE id=? AND receiver_tg_id=? AND status='approved'",(mid,uid))
        if not m:
            if action == 'view':
                old = await self.db.one('''SELECT s.id FROM sessions s JOIN messages m ON m.id=s.message_id
                  WHERE m.id=? AND m.receiver_tg_id=? AND s.status='open' ''',(mid,uid))
                if old:
                    await self.announce(old['id'])
                    return
            await self.send(uid,'Bu rasm mavjud emas yoki allaqachon ko‘rilgan.')
            return
        if action=='decline':
            await self.db.run("UPDATE messages SET status='rejected' WHERE id=?",(mid,))
            await self.block(uid,m['sender_tg_id'])
            await self.send(uid,'Rasm rad etildi, yuboruvchi siz uchun bloklandi. Boshqarish: /bloklar')
            await self.send(m['sender_tg_id'],'Xabar yuborilmadi: oluvchi rad etdi.')
            return
        if not await self.db.available(uid,m['sender_tg_id']):
            await self.send(uid,'Yuboruvchi hozir mavjud emas.')
            return
        u = await self.db.one('SELECT * FROM users WHERE tg_id=?',(m['sender_tg_id'],))
        await self.send(uid,f"📷 Yuboruvchi: {esc(u['first_name'])}")
        await self.show_metadata(uid,m)
        photo = await self.call(uid,self.bot.send_photo,photo=m['file_id'],caption=esc(m['caption']))
        if not photo:
            return
        sid = await self.db.delivered(m,photo.message_id)
        await self.db.log(uid,'suhbat_ochildi',sid)
        await self.announce(sid)

    async def session_callback(self, q, sid, action):
        uid = q.from_user.id
        s = await self.db.one('SELECT * FROM sessions WHERE id=?',(sid,))
        if not s:
            return
        member=uid in (s['party_a'],s['party_b'])
        if action=='close' and (member or uid==await self.admin()):
            await self.close(sid,uid)
        elif action=='block' and member:
            await self.block(uid,self.other(s,uid))
            await self.send(uid,'Suhbatdosh bloklandi. Boshqarish: /bloklar')
        elif action=='report' and member and q.message:
            mapped=await self.db.one('SELECT * FROM relay_map WHERE chat_id=? AND msg_id=? AND session_id=?',(uid,q.message.message_id,sid))
            if not mapped or mapped['from_tg_id']==uid:
                return
            inserted=await self.db.run('INSERT OR IGNORE INTO reports VALUES(?,?,?,?)',(uid,uid,q.message.message_id,time.time()))
            if inserted:
                await self.db.log(uid,'shikoyat',f'{sid}:{q.message.message_id}')
            await self.flush_reports((uid,uid,q.message.message_id))
            await self.send(uid,'Shikoyat saqlandi. Admin xabar qabul qilishi bilan yetkaziladi.' if inserted
                            else 'Bu shikoyat avval saqlangan. Yetkazilmagan bo‘lsa qayta urinish qilindi.')

    async def flush_reports(self, key=None):
        admin = await self.admin()
        if not admin:
            return
        user = await self.db.one('SELECT active,is_blocked FROM users WHERE tg_id=?',(admin,))
        if not user or not user['active'] or user['is_blocked']:
            return
        sql = '''SELECT r.*,rm.session_id FROM reports r
          JOIN relay_map rm ON rm.chat_id=r.chat_id AND rm.msg_id=r.msg_id
          LEFT JOIN report_delivery d ON d.reporter=r.reporter AND d.chat_id=r.chat_id
            AND d.msg_id=r.msg_id AND d.admin_tg_id=?
          WHERE d.delivered_at IS NULL'''
        args = (admin,)
        if key:
            sql += ' AND r.reporter=? AND r.chat_id=? AND r.msg_id=?'
            args += key
        rows = await self.db.all(sql+' ORDER BY r.created_at LIMIT 20',args)
        for r in rows:
            delivery_key = (r['reporter'],r['chat_id'],r['msg_id'],admin)
            await self.db.run('''INSERT OR IGNORE INTO report_delivery
              (reporter,chat_id,msg_id,admin_tg_id) VALUES(?,?,?,?)''',delivery_key)
            state = await self.db.one('''SELECT * FROM report_delivery
              WHERE reporter=? AND chat_id=? AND msg_id=? AND admin_tg_id=?''',delivery_key)
            try:
                if state['header_msg_id'] is None:
                    header = await self.send(admin,f"🚩 Shikoyat: {r['reporter']}, suhbat #{r['session_id']}. Shikoyat qilingan xabar:")
                    if not header:
                        return
                    await self.db.run('''UPDATE report_delivery SET header_msg_id=?
                      WHERE reporter=? AND chat_id=? AND msg_id=? AND admin_tg_id=?''',(header.message_id,)+delivery_key)
                copied = await self.call(admin,self.bot.copy_message,from_chat_id=r['chat_id'],message_id=r['msg_id'],
                    reply_markup=kb([('Suhbatni yopish',f"close:{r['session_id']}")]))
                if not copied:
                    return
                await self.db.run('''UPDATE report_delivery SET delivered_at=?
                  WHERE reporter=? AND chat_id=? AND msg_id=? AND admin_tg_id=?''',(time.time(),)+delivery_key)
            except TelegramAPIError as exc:
                # Matn bazaga olinmaydi; qayta nusxalash uchun faqat ID qoladi.
                await self.db.log(admin,'shikoyat_kutilmoqda',type(exc).__name__)

    async def recover_pending(self, uid=None):
        sql = '''SELECT DISTINCT s.id FROM sessions s JOIN session_notices n ON n.session_id=s.id
          WHERE s.status='open' AND (n.notice_msg_id IS NULL
            OR (n.photo_msg_id IS NOT NULL AND n.controls_sent=0))'''
        args = ()
        if uid is not None:
            sql += ' AND (s.party_a=? OR s.party_b=?)'
            args = (uid,uid)
        for s in await self.db.all(sql+' ORDER BY s.id LIMIT 50',args):
            await self.announce(s['id'])
        if uid is None or uid == await self.admin():
            await self.flush_reports()

    async def request_card(self, rid):
        r=await self.db.one('SELECT r.*,u.first_name,u.username FROM admin_requests r JOIN users u ON u.tg_id=r.tg_id WHERE r.id=?',(rid,))
        admin=await self.admin()
        if admin:
            await self.send(admin,f"Yangi so‘rov #{rid}: {esc(r['first_name'])} {('@'+esc(r['username'])) if r['username'] else ''} ({r['tg_id']}). Qabul qilasizmi?",reply_markup=kb([('Qabul',f'accept:{rid}'),('Rad',f'deny:{rid}')]))

    async def admin_menu(self, uid):
        if uid!=await self.admin():
            await self.send(uid,'Bu bo‘lim faqat admin uchun.')
            return
        mode=await self.db.setting('moderation')=='1'
        await self.send(uid,'🛠 <b>Admin paneli</b>',reply_markup=kb(
            [('📤 Admin sifatida yuborish','new')], [('🖼 Tasdiqlashlar','reviews:0'),('📥 So‘rovlar','requests:0')],
            [('👤 Sender taklif qilish','invite_sender'),('🔗 Receiver havolasi','new_link')],
            [('🚩 Shikoyatlarni yetkazish','reports')],
            [('💬 Faol sessiyalar','asessions:0'),('🔗 Havolalar','links:0')], [('👥 Foydalanuvchilar','users:0')],
            [(f'⚙️ Moderatsiya: {"yoqilgan" if mode else "o‘chirilgan"}',f'moderation:{int(not mode)}')], [('📜 Nazorat','logs')]))

    async def admin_callback(self, uid, data):
        action=data[0]
        if action=='reports':
            await self.flush_reports()
            pending = await self.db.one('''SELECT count(*) n FROM reports r LEFT JOIN report_delivery d
              ON d.reporter=r.reporter AND d.chat_id=r.chat_id AND d.msg_id=r.msg_id AND d.admin_tg_id=?
              WHERE d.delivered_at IS NULL''',(uid,))
            await self.send(uid,f"Yetkazilishi kutilayotgan shikoyatlar: {pending['n']}. Qayta urinish:",
                            reply_markup=kb([('🔄 Qayta urinish','reports')]))
        elif action=='moderation':
            await self.db.set_setting('moderation',int(data[1]))
            await self.db.log(uid,'moderatsiya_sozlama',data[1])
            await self.admin_menu(uid)
        elif action=='globalblock':
            target=int(data[1]); blocked=int(data[2])
            if target==await self.admin():
                await self.send(uid,'Adminni bloklab bo‘lmaydi.')
                return
            await self.db.run('UPDATE users SET is_blocked=? WHERE tg_id=?',(blocked,target))
            if blocked:
                for s in await self.db.active_sessions(target):
                    await self.close(s['id'],uid)
            await self.db.log(uid,'umumiy_blok',f'{target}:{blocked}')
            await self.send(uid,'Foydalanuvchi holati yangilandi.')
        elif action=='logs':
            rows=await self.db.all('SELECT * FROM logs ORDER BY id DESC LIMIT 20')
            lines=[f"{datetime.fromtimestamp(r['created_at'],timezone.utc):%m-%d %H:%M} UTC · {r['actor_tg_id']} · {esc(r['action'])} · {esc(r['meta'])}" for r in rows]
            await self.send(uid,'📜 Oxirgi amallar (matnsiz):\n'+('\n'.join(lines) or 'Hozircha yo‘q.'))
        else:
            page=max(0,int(data[1])); offset=page*8
            if action=='users':
                rows=await self.db.all('SELECT * FROM users ORDER BY created_at DESC LIMIT 9 OFFSET ?',(offset,))
                for u in rows[:8]:
                    await self.send(uid,f"👤 {esc(u['first_name'])} · {u['tg_id']} · {'faol' if u['active'] else 'faol emas'}",reply_markup=kb([
                        ('Blokdan chiqarish' if u['is_blocked'] else 'Bloklash',f'globalblock:{u["tg_id"]}:{int(not u["is_blocked"])}')]))
            elif action=='links':
                counts=await self.db.all('SELECT status,count(*) n FROM links GROUP BY status')
                await self.send(uid,'🔗 Havolalar: '+', '.join(f"{self.link_state(r['status'])}: {r['n']}" for r in counts))
                rows=await self.db.all('SELECT * FROM links ORDER BY created_at DESC LIMIT 9 OFFSET ?',(offset,))
                for r in rows[:8]:
                    await self.show_link(uid,r)
            elif action=='requests':
                rows=await self.db.all("SELECT id FROM admin_requests WHERE status='pending' ORDER BY id LIMIT 9 OFFSET ?",(offset,))
                for r in rows[:8]: await self.request_card(r['id'])
            elif action=='reviews':
                rows=await self.db.all("SELECT id FROM messages WHERE status='pending' ORDER BY id LIMIT 9 OFFSET ?",(offset,))
                for r in rows[:8]: await self.review(r['id'])
            else:
                return
            if not rows: await self.send(uid,'Ro‘yxat bo‘sh.')
            if len(rows)>8:
                await self.send(uid,'Davomi:',reply_markup=kb([('Keyingi ➡️',f'{action}:{page+1}')]))

    async def cleanup(self):
        await self.db.run("UPDATE links SET status='expired' WHERE status='new' AND created_at<=?",(time.time()-self.cfg.ttl,))
        for s in await self.db.all("SELECT id FROM sessions WHERE status='open' AND last_activity<=?",(time.time()-self.cfg.idle,)):
            await self.close(s['id'])

    async def guard(self, event, callback=False):
        async with self.lock:
            try:
                # Muddati o'tgan sessiya 10 daqiqalik fon siklini kutmaydi.
                await self.cleanup()
                await (self.callback(event) if callback else self.message(event))
            except Exception as exc:
                # Exception matni token, URL yoki foydalanuvchi matnini ochishi mumkin.
                logging.error('Amal bajarilmadi: %s',type(exc).__name__)
                await self.db.log(event.from_user.id,'xatolik',type(exc).__name__)
                await self.quiet(event.from_user.id,'Amal oxirigacha bajarilmadi. Holatni /mening, /kirishlar yoki /sessions orqali tekshiring. Keyin qayta urinib ko‘ring.')

    async def background(self):
        while True:
            await asyncio.sleep(600)
            try:
                async with self.lock:
                    await self.cleanup()
                    await self.recover_pending()
            except Exception as exc:
                logging.error('Fon vazifasi: %s',type(exc).__name__)


def dispatcher(app):
    dp=Dispatcher()
    async def on_message(m: Message):
        await app.guard(m)
    async def on_callback(q: CallbackQuery):
        await app.guard(q,True)
    dp.message.register(on_message,F.chat.type=='private')
    dp.callback_query.register(on_callback,F.message.chat.type=='private')
    return dp


async def main():
    cfg=Config.load()
    db=DB(cfg.db_path)
    await db.init(cfg.moderation)
    bot=Bot(cfg.token,default=DefaultBotProperties(parse_mode='HTML'))
    async with bot:
        me=await bot.get_me()
        app=App(bot,db,cfg,me.username)
        web_runner = None
        if cfg.webapp_url:
            from webapp import start_web_app
            web_runner = await start_web_app(app)
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text='Sahifani ochish',web_app=WebAppInfo(url=cfg.webapp_url+'/')))
        await app.cleanup()
        await app.recover_pending()
        await bot.set_my_commands([BotCommand(command=k,description=v) for k,v in [
            ('start','Boshlash'),('yangi','Yangi rasm yuborish'),('kirishlar','Kelgan rasmlar'),
            ('mening','Mening rasmlarim'),('sessions','Faol suhbatlar'),('yopish','Suhbatni yopish'),
            ('bloklash','Suhbatdoshni bloklash'),('bloklar','Shaxsiy bloklar'),('help','Yordam'),('stop','Xabarlarni to‘xtatish'),('admin','Admin paneli')]])
        # Bitta token uchun faqat bitta polling jarayonini ishga tushiring.
        await bot.delete_webhook(drop_pending_updates=False)
        task=asyncio.create_task(app.background())
        logging.warning('Bot ishga tushdi: @%s',me.username)
        app.ready = True
        try:
            await dispatcher(app).start_polling(bot,handle_as_tasks=False)
        finally:
            app.ready = False
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await task
            if web_runner:
                await web_runner.cleanup()


if __name__=='__main__':
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    try:
        asyncio.run(main())
    except (ValueError,TelegramAPIError) as exc:
        print(str(exc) if isinstance(exc,ValueError) else f'Telegramga ulanish amalga oshmadi: {type(exc).__name__}. Token va internetni tekshiring.')
        raise SystemExit(1)
