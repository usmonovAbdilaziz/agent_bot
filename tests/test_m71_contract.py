import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from invitation_store import ceremony_expiry
from test_minimal import n,api,ready
from test_open_link import make_open

def ts(s): return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()

def test_expiry_tashkent_end_plus_24h_and_cap():
    now=ts('2030-11-05T00:00:00'); details={'date':'05.11.2030'}
    assert ceremony_expiry(details,now)==ts('2030-11-06T19:00:00')
    assert ceremony_expiry({'date':'30.12.2035'},now)==now+400*86400

async def test_ceremony_open_and_single_publish_expiry_and_existing_exception(n,api):
    from test_ceremony import start,fill_to_map,finish
    for mode in ['single','open']:
        mid=await start(n);await fill_to_map(n,mid);await finish(n,mid,mode=mode)
        assert 'Havola amal qilish muddati' in n.sent(1)[-1]['text']
        await n.cb(1,f'q:confirm:{mid}');item=await n.db.invite(mid)
        assert abs(item['expires_at']-ceremony_expiry_local(item))<2
        await n.msg(2,f'/start i_{item["token"]}')
        assert (await api('POST',f'/api/invites/{mid}/rsvp',uid=2,json={'attending':1,'guests':1}))[0]==200
        await n.db.run('UPDATE q_invites SET expires_at=0 WHERE id=?',(mid,))
        assert await n.db.claim(item['token'],2)==mid and await n.db.claim(item['token'],3) is None

def ceremony_expiry_local(item):
    import json
    from invitation_store import ceremony_expiry
    return ceremony_expiry(json.loads(item['details']),item['created_at'])

async def test_invalid_type_design_and_legacy_fallback(n,api):
    item=await ready(n);mid=item['id'];await n.msg(2,f'/start i_{item["token"]}')
    await n.db.run("UPDATE q_invites SET design='nafis' WHERE id=?",(mid,))
    assert (await api('GET',f'/api/invites/{mid}',uid=2))[0]==409
    await n.db.run("UPDATE q_invites SET design='old-unknown' WHERE id=?",(mid,))
    assert (await api('GET',f'/api/invites/{mid}',uid=2))[1]['design']=='classic'
    await n.db.run("UPDATE q_invites SET status='draft',design='classic',share_mode='open' WHERE id=?",(mid,))
    assert await n.db.publish(mid,1,3600) is None

async def test_closed_error_has_stable_code(n,api):
    item=await make_open(n);mid=item['id'];await n.msg(2,f'/start i_{item["token"]}')
    details=json.loads(item['details']);details['date']='01.01.2000'
    await n.db.run('UPDATE q_invites SET details=? WHERE id=?',(json.dumps(details),mid))
    status,body=await api('POST',f'/api/invites/{mid}/rsvp',uid=2,json={'attending':1,'guests':1})
    assert status==409 and body['code']=='rsvp_closed'

@pytest.mark.parametrize('mode',['single','open'])
async def test_claim_and_rsvp_at_event_midnight_and_expiry(n,monkeypatch,mode):
    from types import SimpleNamespace
    import invitation_store
    item=await make_open(n);mid=item['id'];expiry=item['expires_at']
    await n.db.run('UPDATE q_invites SET share_mode=? WHERE id=?',(mode,mid))
    event_midnight=expiry-86400
    monkeypatch.setattr(invitation_store,'time',SimpleNamespace(time=lambda:event_midnight-1))
    assert await n.db.claim(item['token'],2)==mid
    monkeypatch.setattr(invitation_store,'time',SimpleNamespace(time=lambda:event_midnight))
    assert await n.db.rsvp(mid,2,1,1,'Guest')=='passed'
    monkeypatch.setattr(invitation_store,'time',SimpleNamespace(time=lambda:expiry-1))
    assert await n.db.claim(item['token'],2)==mid
    monkeypatch.setattr(invitation_store,'time',SimpleNamespace(time=lambda:expiry))
    assert await n.db.claim(item['token'],2) is None
    await n.db.run("INSERT INTO q_rsvps(invite_id,telegram_user_id,attending,guests,responded_at,receiver_name,notice_status) VALUES(?,2,1,1,1,'Guest','sent')",(mid,))
    assert await n.db.claim(item['token'],2)==mid
