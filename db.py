"""SQLite: qisqa tranzaksiyalar, UTC vaqt va atomik holat almashinuvi."""
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(
 tg_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, username TEXT,
 is_blocked INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
 composing INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
 id INTEGER PRIMARY KEY, sender_tg_id INTEGER NOT NULL, receiver_tg_id INTEGER,
 file_id TEXT NOT NULL, caption TEXT, mode TEXT,
 status TEXT NOT NULL DEFAULT 'draft', created_at REAL NOT NULL,
 source_msg_id INTEGER, UNIQUE(sender_tg_id, source_msg_id));
CREATE TABLE IF NOT EXISTS message_inputs(
 tg_id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL,
 field TEXT NOT NULL, after_link INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS links(
 token TEXT PRIMARY KEY, creator_tg_id INTEGER NOT NULL, message_id INTEGER NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'new', claimed_by INTEGER, created_at REAL NOT NULL, claimed_at REAL);
CREATE TABLE IF NOT EXISTS sessions(
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, party_a INTEGER NOT NULL, party_b INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', last_activity REAL NOT NULL, created_at REAL NOT NULL,
 message_id INTEGER UNIQUE, CHECK(party_a != party_b));
CREATE TABLE IF NOT EXISTS admin_requests(
 id INTEGER PRIMARY KEY, tg_id INTEGER NOT NULL, link_token TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS relay_map(
 chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL, session_id INTEGER NOT NULL,
 from_tg_id INTEGER NOT NULL, PRIMARY KEY(chat_id,msg_id));
CREATE TABLE IF NOT EXISTS pair_blocks(
 blocker INTEGER NOT NULL, blocked INTEGER NOT NULL, PRIMARY KEY(blocker,blocked));
CREATE TABLE IF NOT EXISTS reports(
 reporter INTEGER NOT NULL, chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL,
 created_at REAL NOT NULL, PRIMARY KEY(reporter,chat_id,msg_id));
CREATE TABLE IF NOT EXISTS session_notices(
 session_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, notice_msg_id INTEGER,
 photo_msg_id INTEGER, controls_sent INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(session_id,chat_id));
CREATE TABLE IF NOT EXISTS report_delivery(
 reporter INTEGER NOT NULL, chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL,
 admin_tg_id INTEGER NOT NULL, header_msg_id INTEGER, delivered_at REAL,
 PRIMARY KEY(reporter,chat_id,msg_id,admin_tg_id));
CREATE TABLE IF NOT EXISTS logs(
 id INTEGER PRIMARY KEY, actor_tg_id INTEGER, action TEXT NOT NULL, meta TEXT NOT NULL,
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS messages_rate ON messages(sender_tg_id,created_at);
CREATE INDEX IF NOT EXISTS requests_rate ON admin_requests(tg_id,created_at);
CREATE INDEX IF NOT EXISTS sessions_active ON sessions(status,last_activity);
"""


class DB:
    def __init__(self, path):
        self.path = str(path)

    @asynccontextmanager
    async def connect(self, write=False):
        async with aiosqlite.connect(self.path, timeout=15) as c:
            c.row_factory = aiosqlite.Row
            await c.execute('PRAGMA busy_timeout=15000')
            if write:
                await c.execute('BEGIN IMMEDIATE')
            try:
                yield c
                if write:
                    await c.commit()
            except BaseException:
                if write:
                    await c.rollback()
                raise

    async def init(self, moderation=True):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as c:
            await c.executescript(SCHEMA)
            columns = {r[1] for r in await (await c.execute('PRAGMA table_info(messages)')).fetchall()}
            for name in ('title', 'description'):
                if name not in columns:
                    await c.execute(f"ALTER TABLE messages ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            await c.execute("INSERT OR IGNORE INTO settings VALUES('moderation',?)", (str(int(moderation)),))
            # Eski bazani buzmasdan yangi yetkazish navbatini qo'shamiz.
            for party in ('party_a', 'party_b'):
                await c.execute(f'''INSERT OR IGNORE INTO session_notices(session_id,chat_id)
                  SELECT id,{party} FROM sessions WHERE status='open' ''')
            await c.commit()

    async def all(self, sql, args=()):
        async with self.connect() as c:
            return [dict(r) for r in await (await c.execute(sql, args)).fetchall()]

    async def one(self, sql, args=()):
        rows = await self.all(sql, args)
        return rows[0] if rows else None

    async def run(self, sql, args=()):
        async with self.connect(True) as c:
            cur = await c.execute(sql, args)
            return cur.rowcount

    async def setting(self, key):
        r = await self.one('SELECT value FROM settings WHERE key=?', (key,))
        return r['value'] if r else None

    async def set_setting(self, key, value):
        await self.run('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, str(value)))

    async def register(self, user, activate=False):
        await self.run('''INSERT INTO users(tg_id,first_name,username,created_at) VALUES(?,?,?,?)
          ON CONFLICT(tg_id) DO UPDATE SET first_name=excluded.first_name,username=excluded.username''',
                       (user.id, user.first_name, user.username, time.time()))
        if activate:
            await self.run('UPDATE users SET active=1 WHERE tg_id=?', (user.id,))

    async def log(self, actor, action, meta=''):
        # Faqat ID va holatlar; xabar matni yoki telefon yozilmaydi.
        await self.run('INSERT INTO logs(actor_tg_id,action,meta,created_at) VALUES(?,?,?,?)',
                       (actor, action, str(meta), time.time()))

    async def available(self, a, b):
        if a == b:
            return False
        rows = await self.all('SELECT * FROM users WHERE tg_id IN (?,?)', (a, b))
        if len(rows) != 2 or any(r['is_blocked'] or not r['active'] for r in rows):
            return False
        return not await self.one('SELECT 1 FROM pair_blocks WHERE (blocker=? AND blocked=?) OR (blocker=? AND blocked=?)', (a,b,b,a))

    async def draft(self, uid, file_id, caption, source_id):
        async with self.connect(True) as c:
            existing = await (await c.execute('SELECT id FROM messages WHERE sender_tg_id=? AND source_msg_id=?', (uid,source_id))).fetchone()
            if existing:
                return existing['id']
            n = await (await c.execute('SELECT count(*) FROM messages WHERE sender_tg_id=? AND created_at>?', (uid,time.time()-3600))).fetchone()
            if n[0] >= 10:
                return None
            cur = await c.execute('INSERT INTO messages(sender_tg_id,file_id,caption,created_at,source_msg_id) VALUES(?,?,?,?,?)', (uid,file_id,caption,time.time(),source_id))
            await c.execute('UPDATE users SET composing=0 WHERE tg_id=?', (uid,))
            return cur.lastrowid

    async def metadata(self, mid, uid, title, description):
        title, description = title.strip(), description.strip()
        if not 1 <= len(title) <= 120 or not 1 <= len(description) <= 2000:
            raise ValueError('Sarlavha 1–120, tavsif 1–2000 belgidan iborat bo‘lsin.')
        return await self.run('''UPDATE messages SET title=?,description=?
          WHERE id=? AND sender_tg_id=? AND status='draft' ''',(title,description,mid,uid))

    async def claim(self, token, uid, ttl):
        async with self.connect(True) as c:
            r = await (await c.execute('SELECT * FROM links WHERE token=?', (token,))).fetchone()
            if not r:
                return 'invalid', None
            r = dict(r)
            if r['status'] in ('revoked','expired'):
                return 'invalid', r
            if r['status'] == 'new' and r['created_at'] + ttl <= time.time():
                await c.execute("UPDATE links SET status='expired' WHERE token=? AND status='new'", (token,))
                return 'invalid', r
            if r['creator_tg_id'] == uid:
                return 'own', r
            if r['status'] == 'used':
                return 'used', r
            cur = await c.execute("UPDATE links SET status='used',claimed_by=?,claimed_at=? WHERE token=? AND status='new'", (uid,time.time(),token))
            if cur.rowcount != 1:
                return 'used', r
            await c.execute('UPDATE messages SET receiver_tg_id=? WHERE id=?', (uid,r['message_id']))
            return 'won', r

    async def request_admin(self, uid, token):
        async with self.connect(True) as c:
            r = await (await c.execute("SELECT * FROM links WHERE token=? AND status='used'", (token,))).fetchone()
            if not r or uid in (r['creator_tg_id'],r['claimed_by']):
                return None
            old = await (await c.execute('SELECT id FROM admin_requests WHERE tg_id=? AND created_at>?', (uid,time.time()-86400))).fetchone()
            if old:
                return None
            cur = await c.execute('INSERT INTO admin_requests(tg_id,link_token,created_at) VALUES(?,?,?)', (uid,token,time.time()))
            return cur.lastrowid

    async def open_session(self, a, b, kind='user_user', message_id=None):
        async with self.connect(True) as c:
            if message_id:
                old = await (await c.execute('SELECT id FROM sessions WHERE message_id=?', (message_id,))).fetchone()
                if old:
                    return old['id']
            cur = await c.execute('INSERT INTO sessions(kind,party_a,party_b,last_activity,created_at,message_id) VALUES(?,?,?,?,?,?)', (kind,a,b,time.time(),time.time(),message_id))
            sid = cur.lastrowid
            await self.queue_notices(c,sid,a,b)
            return sid

    @staticmethod
    async def queue_notices(c, sid, a, b, photo_msg_id=None):
        # Sessiya va majburiy ogohlantirishlar bitta tranzaksiyada yaratiladi.
        await c.executemany('''INSERT OR IGNORE INTO session_notices
          (session_id,chat_id,photo_msg_id) VALUES(?,?,?)''',
                            [(sid,a,None),(sid,b,photo_msg_id)])

    async def mapping(self, chat, msg, sid, sender):
        await self.run('INSERT OR REPLACE INTO relay_map VALUES(?,?,?,?)', (chat,msg,sid,sender))

    async def delivered(self, m, received_msg_id):
        async with self.connect(True) as c:
            await c.execute("UPDATE messages SET status='delivered' WHERE id=?",(m['id'],))
            cur = await c.execute("INSERT INTO sessions(kind,party_a,party_b,last_activity,created_at,message_id) VALUES('user_user',?,?,?,?,?)",
                                  (m['sender_tg_id'],m['receiver_tg_id'],time.time(),time.time(),m['id']))
            sid=cur.lastrowid
            if received_msg_id is not None:
                await c.execute('INSERT INTO relay_map VALUES(?,?,?,?)',(m['receiver_tg_id'],received_msg_id,sid,m['sender_tg_id']))
            await self.queue_notices(c,sid,m['sender_tg_id'],m['receiver_tg_id'],received_msg_id)
            return sid

    async def accept_request(self, rid, admin):
        async with self.connect(True) as c:
            r=await (await c.execute("SELECT * FROM admin_requests WHERE id=? AND status='pending'",(rid,))).fetchone()
            if not r:
                return None
            await c.execute("UPDATE admin_requests SET status='accepted' WHERE id=?",(rid,))
            cur=await c.execute("INSERT INTO sessions(kind,party_a,party_b,last_activity,created_at) VALUES('admin_user',?,?,?,?)",
                                (admin,r['tg_id'],time.time(),time.time()))
            sid=cur.lastrowid
            await self.queue_notices(c,sid,admin,r['tg_id'])
            return sid

    async def active_sessions(self, uid):
        return await self.all("SELECT * FROM sessions WHERE status='open' AND (party_a=? OR party_b=?) ORDER BY id DESC", (uid,uid))

    async def resolve(self, uid, reply_id=None):
        if reply_id is not None:
            return await self.one('''SELECT s.* FROM relay_map r JOIN sessions s ON s.id=r.session_id
              WHERE r.chat_id=? AND r.msg_id=? AND (s.party_a=? OR s.party_b=?)''', (uid,reply_id,uid,uid))
        rows = await self.active_sessions(uid)
        return rows[0] if len(rows) == 1 else None
