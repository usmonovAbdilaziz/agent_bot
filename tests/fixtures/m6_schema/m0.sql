-- Generated from 938a52c by historical DB init.
BEGIN TRANSACTION;
CREATE TABLE admin_requests(
 id INTEGER PRIMARY KEY, tg_id INTEGER NOT NULL, link_token TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL);
CREATE TABLE links(
 token TEXT PRIMARY KEY, creator_tg_id INTEGER NOT NULL, message_id INTEGER NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'new', claimed_by INTEGER, created_at REAL NOT NULL, claimed_at REAL);
CREATE TABLE logs(
 id INTEGER PRIMARY KEY, actor_tg_id INTEGER, action TEXT NOT NULL, meta TEXT NOT NULL,
 created_at REAL NOT NULL);
CREATE TABLE message_inputs(
 tg_id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL,
 field TEXT NOT NULL, after_link INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages(
 id INTEGER PRIMARY KEY, sender_tg_id INTEGER NOT NULL, receiver_tg_id INTEGER,
 file_id TEXT NOT NULL, caption TEXT, mode TEXT,
 status TEXT NOT NULL DEFAULT 'draft', created_at REAL NOT NULL,
 source_msg_id INTEGER, title TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', UNIQUE(sender_tg_id, source_msg_id));
CREATE TABLE pair_blocks(
 blocker INTEGER NOT NULL, blocked INTEGER NOT NULL, PRIMARY KEY(blocker,blocked));
CREATE TABLE q_accept_notices(
 invite_id INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE q_done(uid INTEGER PRIMARY KEY, completed_at REAL NOT NULL);
CREATE TABLE q_flows(uid INTEGER PRIMARY KEY, stage TEXT NOT NULL, invite_id INTEGER);
CREATE TABLE q_invites(
 id INTEGER PRIMARY KEY, sender INTEGER NOT NULL, receiver INTEGER,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 media_kind TEXT NOT NULL DEFAULT 'none', file_id TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'draft', token TEXT UNIQUE,
 created_at REAL NOT NULL, expires_at REAL, accepted_at REAL, link_sent INTEGER NOT NULL DEFAULT 0, no_attempts INTEGER NOT NULL DEFAULT 0, design TEXT NOT NULL DEFAULT 'classic', type TEXT NOT NULL DEFAULT 'fun', details TEXT NOT NULL DEFAULT '{}');
INSERT INTO "q_invites" VALUES(1,1,2,'Old','Hello','none','','ready','old-token',1.0,4102444800.0,NULL,0,0,'classic','fun','{}');
CREATE TABLE q_phone_grants(phone_hash TEXT PRIMARY KEY);
CREATE TABLE q_profiles(uid INTEGER PRIMARY KEY, full_name TEXT NOT NULL, phone_hash TEXT UNIQUE);
CREATE TABLE q_registration(uid INTEGER PRIMARY KEY, phone TEXT NOT NULL);
CREATE TABLE q_seen(uid INTEGER NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(uid,message_id));
CREATE TABLE q_sender_credits(uid INTEGER PRIMARY KEY, remaining INTEGER NOT NULL CHECK(remaining >= 0));
CREATE TABLE q_sender_requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL,
 admin_notified INTEGER NOT NULL DEFAULT 0, decision_notified INTEGER NOT NULL DEFAULT 0, quantity INTEGER NOT NULL DEFAULT 1, phone TEXT NOT NULL DEFAULT '');
CREATE TABLE q_senders(uid INTEGER PRIMARY KEY);
CREATE TABLE q_suggestion_drafts(uid INTEGER PRIMARY KEY);
CREATE TABLE q_suggestions(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, body TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL, admin_notified INTEGER NOT NULL DEFAULT 0,
 decision_notified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE relay_map(
 chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL, session_id INTEGER NOT NULL,
 from_tg_id INTEGER NOT NULL, PRIMARY KEY(chat_id,msg_id));
CREATE TABLE report_delivery(
 reporter INTEGER NOT NULL, chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL,
 admin_tg_id INTEGER NOT NULL, header_msg_id INTEGER, delivered_at REAL,
 PRIMARY KEY(reporter,chat_id,msg_id,admin_tg_id));
CREATE TABLE reports(
 reporter INTEGER NOT NULL, chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL,
 created_at REAL NOT NULL, PRIMARY KEY(reporter,chat_id,msg_id));
CREATE TABLE session_notices(
 session_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, notice_msg_id INTEGER,
 photo_msg_id INTEGER, controls_sent INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(session_id,chat_id));
CREATE TABLE sessions(
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, party_a INTEGER NOT NULL, party_b INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', last_activity REAL NOT NULL, created_at REAL NOT NULL,
 message_id INTEGER UNIQUE, CHECK(party_a != party_b));
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO "settings" VALUES('moderation','1');
INSERT INTO "settings" VALUES('q_one_link_permissions','1');
CREATE TABLE users(
 tg_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, username TEXT,
 is_blocked INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
 composing INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE INDEX messages_rate ON messages(sender_tg_id,created_at);
CREATE INDEX requests_rate ON admin_requests(tg_id,created_at);
CREATE INDEX sessions_active ON sessions(status,last_activity);
CREATE UNIQUE INDEX q_one_draft ON q_invites(sender) WHERE status='draft';
CREATE UNIQUE INDEX q_one_sender_request ON q_sender_requests(uid) WHERE status='pending';
DELETE FROM "sqlite_sequence";
COMMIT;
