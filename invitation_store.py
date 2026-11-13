"""Minimal invitation state; additive tables preserve the previous database."""
import secrets
import time
from db import DB
from designs import valid_design
from wedding import validated_details, expires_at

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
CREATE TABLE IF NOT EXISTS q_wedding_guests(invite_id INTEGER NOT NULL, uid INTEGER NOT NULL,
 viewed_at REAL, PRIMARY KEY(invite_id,uid));
CREATE TABLE IF NOT EXISTS q_accept_notices(
 invite_id INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS q_sender_requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL,
 admin_notified INTEGER NOT NULL DEFAULT 0, decision_notified INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS q_one_sender_request ON q_sender_requests(uid) WHERE status='pending';
"""

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
            request_columns = {r[1] for r in await (await c.execute('PRAGMA table_info(q_sender_requests)')).fetchall()}
            if 'quantity' not in request_columns:
                await c.execute('ALTER TABLE q_sender_requests ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1')
            if 'phone' not in request_columns:
                await c.execute("ALTER TABLE q_sender_requests ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
            # One-time privacy cleanup for requests already decided before retention was added.
            cleanup = await (await c.execute("SELECT 1 FROM settings WHERE key='q_decided_request_phone_cleanup'")).fetchone()
            if not cleanup:
                await c.execute("UPDATE q_sender_requests SET phone='' WHERE status!='pending'")
                await c.execute("INSERT INTO settings VALUES('q_decided_request_phone_cleanup','1')")
            await c.execute('INSERT OR IGNORE INTO q_sender_credits(uid,remaining) SELECT uid,1 FROM q_senders')
            migrated = await (await c.execute("SELECT 1 FROM settings WHERE key='q_one_link_permissions'")).fetchone()
            if not migrated:
                # Old phone grants were permanent; do not let contact replay renew them.
                await c.execute('DELETE FROM q_phone_grants WHERE phone_hash IN (SELECT phone_hash FROM q_profiles WHERE phone_hash IS NOT NULL)')
                await c.execute("INSERT INTO settings VALUES('q_one_link_permissions','1')")
            await c.commit()

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
            await c.execute("UPDATE q_sender_requests SET status=?,phone='' WHERE id=?",(status,request_id))
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

    async def begin(self, uid, invite_type='fun'):
        async with self.connect(True) as c:
            if not await self._can_publish(c,uid): return None
            row = await (await c.execute("SELECT id FROM q_invites WHERE sender=? AND status='draft'",(uid,))).fetchone()
            if row:
                mid = row['id']
            else:
                name = await (await c.execute('SELECT full_name FROM q_profiles WHERE uid=?',(uid,))).fetchone()
                design = 'wedding_classic' if invite_type == 'ceremony' else 'classic'
                cur = await c.execute('INSERT INTO q_invites(sender,title,created_at,type,design) VALUES(?,?,?,?,?)',(uid,name[0][:120],time.time(),invite_type,design))
                mid = cur.lastrowid
            stage = 'wedding_groom' if invite_type == 'ceremony' else 'media'
            await c.execute('INSERT OR IGNORE INTO q_flows VALUES(?,?,?)',(uid,stage,mid))
        return mid

    async def invite(self, mid):
        return await self.one('SELECT * FROM q_invites WHERE id=?',(mid,))

    async def publish(self, mid, uid, ttl):
        async with self.connect(True) as c:
            row = await (await c.execute('SELECT * FROM q_invites WHERE id=? AND sender=?',(mid,uid))).fetchone()
            details = validated_details(row['details']) if row and row['type']=='ceremony' else None
            if not row or not valid_design(row['design'], row['type']) or (row['type']=='fun' and not row['description'].strip()) or (row['type']=='ceremony' and not details):
                return None
            if row['status']=='draft':
                if not await self._can_publish(c,uid): return None
                expiry = expires_at(details) if details else time.time()+ttl
                if expiry <= time.time(): return None
                await c.execute("UPDATE q_invites SET status='ready',token=?,expires_at=? WHERE id=?",(secrets.token_urlsafe(18),expiry,mid))
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
            if not row or row['status']!='ready' or row['expires_at']<=time.time():
                return None
            if row['sender']==uid:
                return None
            if row['type']=='ceremony':
                await c.execute('INSERT OR IGNORE INTO q_wedding_guests(invite_id,uid) VALUES(?,?)',(row['id'],uid))
                return row['id']
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
            if not row: return False
            if row['status']=='accepted': return True
            if row['status']!='ready' or row['expires_at']<=time.time(): return False
            await c.execute("UPDATE q_invites SET status='accepted',accepted_at=?,no_attempts=? WHERE id=?",(time.time(),no_attempts,mid))
            await c.execute('INSERT OR IGNORE INTO q_done VALUES(?,?)',(uid,time.time()))
            await c.execute('INSERT OR IGNORE INTO q_accept_notices(invite_id) VALUES(?)',(mid,))
            return True
