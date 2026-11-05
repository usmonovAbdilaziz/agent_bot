"""Minimal invitation state; additive tables preserve the previous database."""
import json
import secrets
import time
import re
import html
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from db import DB
from designs import valid_design

SCHEMA = """
CREATE TABLE IF NOT EXISTS q_profiles(uid INTEGER PRIMARY KEY, full_name TEXT NOT NULL, phone_hash TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS q_senders(uid INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS q_sender_credits(uid INTEGER PRIMARY KEY, remaining INTEGER NOT NULL CHECK(remaining >= 0));
CREATE TABLE IF NOT EXISTS q_registration(uid INTEGER PRIMARY KEY, phone TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS q_suggestion_drafts(uid INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS q_suggestions(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, body TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL, admin_notified INTEGER NOT NULL DEFAULT 0,
 decision_notified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS q_phone_grants(phone_hash TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS q_invites(
 id INTEGER PRIMARY KEY, sender INTEGER NOT NULL, receiver INTEGER,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 media_kind TEXT NOT NULL DEFAULT 'none', file_id TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'draft', token TEXT UNIQUE,
 created_at REAL NOT NULL, expires_at REAL, accepted_at REAL, link_sent INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS q_one_draft ON q_invites(sender) WHERE status='draft';
CREATE TABLE IF NOT EXISTS q_flows(uid INTEGER PRIMARY KEY, stage TEXT NOT NULL, invite_id INTEGER);
CREATE TABLE IF NOT EXISTS q_done(uid INTEGER PRIMARY KEY, completed_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS q_seen(uid INTEGER NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(uid,message_id));
CREATE TABLE IF NOT EXISTS q_accept_notices(
 invite_id INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS q_rsvps(
 invite_id INTEGER PRIMARY KEY REFERENCES q_invites(id), attending INTEGER NOT NULL CHECK(attending IN (0,1)),
 guests INTEGER NOT NULL CHECK(guests BETWEEN 0 AND 10), responded_at REAL NOT NULL,
 receiver_name TEXT NOT NULL, notice_status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS q_sender_requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL,
 admin_notified INTEGER NOT NULL DEFAULT 0, decision_notified INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS q_one_sender_request ON q_sender_requests(uid) WHERE status='pending';
"""

def parse_details(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    layout = value.get('layout', {})
    if not isinstance(layout, dict) or layout.get('text_position', 'bottom') not in ('bottom', 'center', 'top'):
        return None
    return value

EVENT_KINDS = ('wedding', 'nikah', 'beshik', 'sunnat', 'fotiha', 'birthday', 'other')
MAP_HOSTS = {'maps.google.com', 'maps.google.co.uz', 'maps.app.goo.gl', 'goo.gl',
             'yandex.uz', 'yandex.ru', 'yandex.com', 'maps.yandex.ru', 'maps.yandex.com',
             '2gis.uz', '2gis.ru', '2gis.com', 'go.2gis.com'}

def valid_map_url(value):
    if not isinstance(value, str) or not value or len(value)>500 or any(c.isspace() or ord(c)<32 for c in value): return False
    try:
        url=urlsplit(value)
        if url.scheme!='https' or url.hostname not in MAP_HOSTS or url.username is not None or url.password is not None or url.port not in (None,443): return False
        if url.hostname in {'yandex.uz','yandex.ru','yandex.com'} and not url.path.startswith('/maps'): return False
        if url.hostname=='goo.gl' and not url.path.startswith('/maps/'): return False
        return True
    except ValueError:
        return False

def valid_ceremony_details(value, *, complete=False, check_date=False):
    if not isinstance(value,dict) or set(value)-{'event_kind','date','time','address','map_url','program','note','layout'}: return False
    if parse_details(json.dumps(value)) is None: return False
    if 'layout' in value and set(value['layout'])-{'text_position'}: return False
    if complete and not {'event_kind','date','time','address','map_url','program','note','layout'} <= value.keys(): return False
    if 'event_kind' in value and value['event_kind'] not in EVENT_KINDS: return False
    if 'date' in value:
        if not isinstance(value['date'],str) or not re.fullmatch(r'\d{2}\.\d{2}\.\d{4}',value['date']): return False
        try: date=datetime.strptime(value['date'],'%d.%m.%Y').date()
        except ValueError: return False
        if check_date and date < datetime.now(ZoneInfo('Asia/Tashkent')).date(): return False
    if 'time' in value:
        if not isinstance(value['time'],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value['time']): return False
    for key, limit in (('address',300),('note',500)):
        if key in value and (not isinstance(value[key],str) or not value[key].strip() or len(value[key])>limit): return False
    if 'map_url' in value and value['map_url']!='' and not valid_map_url(value['map_url']): return False
    if 'program' in value and (not isinstance(value['program'],list) or len(value['program'])>20 or any(not isinstance(x,str) or not x.strip() or len(x)>200 for x in value['program']) or sum(map(len,value['program']))>800): return False
    # Telegram messages are limited to 4096 characters after HTML escaping.
    texts=[value.get(key,'') for key in ('address','map_url','note')] + value.get('program',[])
    if sum(len(html.escape(text)) for text in texts)>2800: return False
    return True


def ceremony_expiry(details, now=None):
    now=time.time() if now is None else now
    event=datetime.strptime(details['date'],'%d.%m.%Y').date()
    try:
        end=datetime.combine(event+timedelta(days=2),dt_time.min,tzinfo=ZoneInfo('Asia/Tashkent')).timestamp()
    except (OverflowError, ValueError):
        return now+400*86400
    return min(end,now+400*86400)


def ceremony_passed(details, now=None):
    try:
        event_date=datetime.strptime(details['date'],'%d.%m.%Y').date()
        current=datetime.fromtimestamp(time.time() if now is None else now,ZoneInfo('Asia/Tashkent')).date()
        return current > event_date
    except (TypeError, ValueError, KeyError):
        return True


class InvitationDB(DB):
    async def init(self, moderation=True):
        await super().init(moderation)
        async with self.connect() as c:
            await c.executescript(SCHEMA)
            columns = {r[1] for r in await (await c.execute('PRAGMA table_info(q_invites)')).fetchall()}
            if 'link_sent' not in columns:
                await c.execute('ALTER TABLE q_invites ADD COLUMN link_sent INTEGER NOT NULL DEFAULT 0')
            if 'no_attempts' not in columns:
                await c.execute('ALTER TABLE q_invites ADD COLUMN no_attempts INTEGER NOT NULL DEFAULT 0')
            if 'design' not in columns:
                await c.execute("ALTER TABLE q_invites ADD COLUMN design TEXT NOT NULL DEFAULT 'classic'")
            if 'type' not in columns:
                await c.execute("ALTER TABLE q_invites ADD COLUMN type TEXT NOT NULL DEFAULT 'fun'")
            if 'details' not in columns:
                await c.execute("ALTER TABLE q_invites ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
            if 'share_mode' not in columns:
                await c.execute("ALTER TABLE q_invites ADD COLUMN share_mode TEXT NOT NULL DEFAULT 'single' CHECK(share_mode IN ('single','open'))")
            # executescript commits implicitly, so begin only after schema bootstrap.
            await c.execute('BEGIN IMMEDIATE')
            try:
                await self._migrate_rsvps(c)
                await c.commit()
            except BaseException:
                await c.rollback()
                raise
            await c.execute('CREATE TABLE IF NOT EXISTS q_open_views(invite_id INTEGER NOT NULL, telegram_user_id INTEGER NOT NULL, PRIMARY KEY(invite_id,telegram_user_id))')
            await c.execute("UPDATE q_invites SET design='nafis' WHERE type='ceremony' AND design='ceremony_elegant'")
            request_columns = {r[1] for r in await (await c.execute('PRAGMA table_info(q_sender_requests)')).fetchall()}
            if 'quantity' not in request_columns:
                await c.execute('ALTER TABLE q_sender_requests ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1')
            if 'phone' not in request_columns:
                await c.execute("ALTER TABLE q_sender_requests ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
            await c.execute('INSERT OR IGNORE INTO q_sender_credits(uid,remaining) SELECT uid,1 FROM q_senders')
            migrated = await (await c.execute("SELECT 1 FROM settings WHERE key='q_one_link_permissions'")).fetchone()
            if not migrated:
                # Old phone grants were permanent; do not let contact replay renew them.
                await c.execute('DELETE FROM q_phone_grants WHERE phone_hash IN (SELECT phone_hash FROM q_profiles WHERE phone_hash IS NOT NULL)')
                await c.execute("INSERT INTO settings VALUES('q_one_link_permissions','1')")
            await c.commit()

    async def _migration_step(self, step):
        """Test seam for interruption before transaction commit."""

    async def _migrate_rsvps(self, c):
        async def columns(table):
            return {r[1] for r in await (await c.execute(f'PRAGMA table_info({table})')).fetchall()}
        old_exists=bool(await (await c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='q_rsvps_old'")).fetchone())
        current_columns=await columns('q_rsvps')
        if not old_exists and 'telegram_user_id' in current_columns: return
        if not old_exists:
            await c.execute('ALTER TABLE q_rsvps RENAME TO q_rsvps_old')
            await self._migration_step('rename')
        elif 'telegram_user_id' not in current_columns:
            # Bootstrap can recreate an empty legacy table after an interrupted rename.
            if await (await c.execute('SELECT 1 FROM q_rsvps LIMIT 1')).fetchone():
                raise RuntimeError('Both legacy RSVP tables contain data; manual recovery required')
            await c.execute('DROP TABLE q_rsvps')
        await c.execute("""CREATE TABLE IF NOT EXISTS q_rsvps (
            invite_id INTEGER NOT NULL REFERENCES q_invites(id), telegram_user_id INTEGER,
            attending INTEGER NOT NULL CHECK(attending IN (0,1)),
            guests INTEGER NOT NULL CHECK(guests BETWEEN 0 AND 10), responded_at REAL NOT NULL,
            receiver_name TEXT NOT NULL, notice_status TEXT NOT NULL DEFAULT 'pending',
            UNIQUE(invite_id,telegram_user_id))""")
        await self._migration_step('create')
        rows=await (await c.execute("""SELECT r.invite_id,i.receiver AS telegram_user_id,r.attending,r.guests,
            r.responded_at,r.receiver_name,r.notice_status FROM q_rsvps_old r
            LEFT JOIN q_invites i ON i.id=r.invite_id""")).fetchall()
        for row in rows:
            existing=await (await c.execute('SELECT attending,guests,responded_at,receiver_name,notice_status FROM q_rsvps WHERE invite_id=? AND telegram_user_id IS ?', (row['invite_id'],row['telegram_user_id']))).fetchone()
            values=tuple(row[k] for k in ('attending','guests','responded_at','receiver_name','notice_status'))
            if existing and tuple(existing)!=values:
                raise RuntimeError('Conflicting RSVP recovery rows; manual recovery required')
            if not existing:
                await c.execute('INSERT INTO q_rsvps VALUES(?,?,?,?,?,?,?)',(row['invite_id'],row['telegram_user_id'],*values))
        await self._migration_step('insert')
        await self._migration_step('before_drop')
        await c.execute('DROP TABLE q_rsvps_old')

    async def sender_request(self, uid, quantity=1):
        async with self.connect(True) as c:
            if quantity not in (1,10,30): return None
            registration = await (await c.execute('SELECT phone FROM q_registration WHERE uid=?',(uid,))).fetchone()
            if not registration or not registration['phone']: return None
            if await (await c.execute('SELECT 1 FROM q_senders WHERE uid=?',(uid,))).fetchone():
                return None
            await c.execute('INSERT OR IGNORE INTO q_sender_requests(uid,created_at,quantity,phone) VALUES(?,?,?,?)',(uid,time.time(),quantity,registration['phone']))
            await c.execute('DELETE FROM q_registration WHERE uid=?',(uid,))
            return await (await c.execute("SELECT * FROM q_sender_requests WHERE uid=? AND status='pending'",(uid,))).fetchone()

    async def _grant(self,c,uid,quantity):
        await c.execute('INSERT INTO q_sender_credits(uid,remaining) VALUES(?,?) ON CONFLICT(uid) DO UPDATE SET remaining=remaining+excluded.remaining',(uid,quantity))
        await c.execute('INSERT OR IGNORE INTO q_senders VALUES(?)',(uid,))

    async def decide_sender(self, request_id, admin_uid, approve):
        async with self.connect(True) as c:
            admin = await (await c.execute("SELECT value FROM settings WHERE key='admin'")).fetchone()
            if not admin or str(admin_uid)!=admin[0]: return None
            row = await (await c.execute('SELECT * FROM q_sender_requests WHERE id=?',(request_id,))).fetchone()
            if not row or row['status']!='pending': return None
            user = await (await c.execute('SELECT is_blocked FROM users WHERE tg_id=?',(row['uid'],))).fetchone()
            if approve and (not user or user[0]): return None
            status = 'approved' if approve else 'denied'
            await c.execute('UPDATE q_sender_requests SET status=? WHERE id=?',(status,request_id))
            if approve:
                await self._grant(c,row['uid'],row['quantity'])
            return row['uid']

    async def grant_phone(self, digest):
        async with self.connect(True) as c:
            target = await (await c.execute('SELECT uid FROM q_profiles WHERE phone_hash=?',(digest,))).fetchone()
            if not target:
                await c.execute('INSERT OR IGNORE INTO q_phone_grants VALUES(?)',(digest,))
                return None
            await c.execute('DELETE FROM q_phone_grants WHERE phone_hash=?',(digest,))
            if not await (await c.execute('SELECT 1 FROM q_senders WHERE uid=?',(target['uid'],))).fetchone():
                await self._grant(c,target['uid'],1)
            return target['uid']

    async def redeem_phone(self, uid, digest):
        async with self.connect(True) as c:
            bound = await (await c.execute('SELECT 1 FROM q_profiles WHERE uid=? AND phone_hash=?',(uid,digest))).fetchone()
            if not bound: return False
            deleted = await c.execute('DELETE FROM q_phone_grants WHERE phone_hash=?',(digest,))
            if not deleted.rowcount: return False
            if not await (await c.execute('SELECT 1 FROM q_senders WHERE uid=?',(uid,))).fetchone():
                await self._grant(c,uid,1)
            return True

    async def _can_publish(self, c, uid):
        admin = await (await c.execute("SELECT value FROM settings WHERE key='admin'")).fetchone()
        return bool((admin and admin[0]==str(uid)) or
                    await (await c.execute('SELECT 1 FROM q_senders WHERE uid=?',(uid,))).fetchone())

    async def profile(self, user):
        await self.register(user, activate=True)
        name = ' '.join(filter(None, [user.first_name, getattr(user, 'last_name', None)]))
        await self.run('''INSERT INTO q_profiles(uid,full_name) VALUES(?,?)
          ON CONFLICT(uid) DO UPDATE SET full_name=excluded.full_name''', (user.id,name))

    async def flow(self, uid):
        return await self.one('SELECT * FROM q_flows WHERE uid=?', (uid,))

    async def stage(self, uid, stage, mid=None):
        await self.run('INSERT OR REPLACE INTO q_flows VALUES(?,?,?)', (uid,stage,mid))

    async def begin(self, uid):
        async with self.connect(True) as c:
            if not await self._can_publish(c,uid): return None
            row = await (await c.execute("SELECT id FROM q_invites WHERE sender=? AND status='draft'",(uid,))).fetchone()
            if row:
                mid = row['id']
            else:
                name = await (await c.execute('SELECT full_name FROM q_profiles WHERE uid=?',(uid,))).fetchone()
                cur = await c.execute('INSERT INTO q_invites(sender,title,created_at) VALUES(?,?,?)',(uid,name[0][:120],time.time()))
                mid = cur.lastrowid
            await c.execute("INSERT OR IGNORE INTO q_flows VALUES(?,'type',?)",(uid,mid))
        return mid

    async def invite(self, mid):
        return await self.one('SELECT * FROM q_invites WHERE id=?',(mid,))

    async def update_ceremony_details(self, mid, uid, updates):
        async with self.connect(True) as c:
            row=await (await c.execute("SELECT details FROM q_invites WHERE id=? AND sender=? AND status='draft' AND type='ceremony'",(mid,uid))).fetchone()
            if not row: return False
            details=parse_details(row['details'])
            if details is None: return False
            details.update(updates)
            if not valid_ceremony_details(details,check_date='date' in updates): return False
            await c.execute('UPDATE q_invites SET details=? WHERE id=?',(json.dumps(details,ensure_ascii=False),mid))
            return True

    async def publish(self, mid, uid, ttl):
        async with self.connect(True) as c:
            row = await (await c.execute('SELECT * FROM q_invites WHERE id=? AND sender=?',(mid,uid))).fetchone()
            if not row or not row['title'].strip() or len(row['title'])>120 or not row['description'].strip() or not valid_design(row['design'], row['type']) or parse_details(row['details']) is None:
                return None
            if row['type']=='fun' and row['share_mode']!='single': return None
            if row['share_mode'] not in ('single','open'): return None
            if row['type']=='ceremony' and (not valid_ceremony_details(parse_details(row['details']),complete=True,check_date=True) or row['description']!=parse_details(row['details'])['note']):
                return None
            if row['status']=='draft':
                if not await self._can_publish(c,uid): return None
                await c.execute("UPDATE q_invites SET status='ready',token=?,expires_at=? WHERE id=?",(secrets.token_urlsafe(18),ceremony_expiry(parse_details(row['details'])) if row['type']=='ceremony' else time.time()+ttl,mid))
                admin = await (await c.execute("SELECT value FROM settings WHERE key='admin'")).fetchone()
                if not admin or admin[0]!=str(uid):
                    credit = await (await c.execute('SELECT remaining FROM q_sender_credits WHERE uid=?',(uid,))).fetchone()
                    if credit and credit['remaining']>1:
                        await c.execute('UPDATE q_sender_credits SET remaining=remaining-1 WHERE uid=?',(uid,))
                    else:
                        await c.execute('DELETE FROM q_sender_credits WHERE uid=?',(uid,))
                        await c.execute('DELETE FROM q_senders WHERE uid=?',(uid,))
            await c.execute('DELETE FROM q_flows WHERE uid=? AND invite_id=?',(uid,mid))
        return await self.invite(mid)

    async def claim(self, token, uid, ttl=None):
        async with self.connect(True) as c:
            row = await (await c.execute('SELECT * FROM q_invites WHERE token=?',(token,))).fetchone()
            if not row or row['status']!='ready' or row['sender']==uid: return None
            if row['expires_at']<=time.time():
                if row['type']!='ceremony' or not await (await c.execute('SELECT 1 FROM q_rsvps WHERE invite_id=? AND telegram_user_id=?',(row['id'],uid))).fetchone(): return None
            if row['share_mode']=='open' and row['type']=='ceremony':
                await c.execute('INSERT OR IGNORE INTO q_open_views VALUES(?,?)',(row['id'],uid))
            else:
                if row['receiver'] not in (None,uid): return None
                await c.execute('UPDATE q_invites SET receiver=? WHERE id=? AND receiver IS NULL',(uid,row['id']))
            return row['id']

    async def decide_suggestion(self, suggestion_id, admin_uid, approve):
        async with self.connect(True) as c:
            admin=await (await c.execute("SELECT value FROM settings WHERE key='admin'")).fetchone()
            if not admin or admin[0]!=str(admin_uid): return None
            row=await (await c.execute('SELECT * FROM q_suggestions WHERE id=?',(suggestion_id,))).fetchone()
            if not row or row['status']!='pending': return None
            user=await (await c.execute('SELECT is_blocked FROM users WHERE tg_id=?',(row['uid'],))).fetchone()
            if approve and (not user or user[0]): return None
            await c.execute('UPDATE q_suggestions SET status=? WHERE id=?',('approved' if approve else 'denied',suggestion_id))
            if approve: await self._grant(c,row['uid'],1)
            return row['uid']

    async def accept(self, mid, uid, no_attempts=0):
        async with self.connect(True) as c:
            row = await (await c.execute('SELECT * FROM q_invites WHERE id=? AND receiver=?',(mid,uid))).fetchone()
            if not row or row['type']!='fun': return False
            if row['status']=='accepted': return True
            if row['status']!='ready' or row['expires_at']<=time.time(): return False
            await c.execute("UPDATE q_invites SET status='accepted',accepted_at=?,no_attempts=? WHERE id=?",(time.time(),no_attempts,mid))
            await c.execute('INSERT OR IGNORE INTO q_done VALUES(?,?)',(uid,time.time()))
            await c.execute('INSERT OR IGNORE INTO q_accept_notices(invite_id) VALUES(?)',(mid,))
            return True

    async def rsvp(self, mid, uid, attending, guests, receiver_name, max_responses=500):
        if type(attending) is not int or attending not in (0,1) or type(guests) is not int or (attending and not 1<=guests<=10) or (not attending and guests!=0): return None
        async with self.connect(True) as c:
            invite=await (await c.execute('SELECT * FROM q_invites WHERE id=?',(mid,))).fetchone()
            if not invite or invite['type']!='ceremony' or invite['status']!='ready' or uid==invite['sender']: return None
            if invite['share_mode']=='single' and invite['receiver']!=uid: return None
            if invite['share_mode']=='open' and not await (await c.execute('SELECT 1 FROM q_open_views WHERE invite_id=? AND telegram_user_id=?',(mid,uid))).fetchone(): return None
            previous=await (await c.execute('SELECT attending,guests,responded_at FROM q_rsvps WHERE invite_id=? AND telegram_user_id=?',(mid,uid))).fetchone()
            if previous: return dict(previous)
            if ceremony_passed(parse_details(invite['details'])): return 'passed'
            if invite['expires_at']<=time.time(): return None
            count=(await (await c.execute('SELECT count(*) FROM q_rsvps WHERE invite_id=?',(mid,))).fetchone())[0]
            if count>=max_responses: return 'limit'
            await c.execute('INSERT INTO q_rsvps(invite_id,telegram_user_id,attending,guests,responded_at,receiver_name,notice_status) VALUES(?,?,?,?,?,?,?)',
                            (mid,uid,attending,guests,time.time(),receiver_name[:200], 'pending' if count<50 else 'suppressed'))
            row=await (await c.execute('SELECT attending,guests,responded_at FROM q_rsvps WHERE invite_id=? AND telegram_user_id=?',(mid,uid))).fetchone()
            return dict(row)
