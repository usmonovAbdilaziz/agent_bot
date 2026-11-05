import json
from test_minimal import n

async def test_check_selects_type_for_sender_and_button(n):
    await n.msg(1,'/check');flow=await n.db.flow(1);mid=flow['invite_id']
    assert flow['stage']=='type'
    keyboard=json.loads(n.sent(1)[-1]['reply_markup'])['inline_keyboard']
    assert {b.get('callback_data') for row in keyboard for b in row}>={f'q:ctype:{mid}:fun',f'q:ctype:{mid}:ceremony'}
    await n.cb(1,'q:check');assert (await n.db.flow(1))['stage']=='type'
    await n.cb(1,f'q:ctype:{mid}:ceremony');assert (await n.db.flow(1))['stage']=='c_kind'

async def test_check_preserves_active_draft_and_requires_sender(n):
    await n.msg(1,'/check');mid=(await n.db.flow(1))['invite_id']
    await n.cb(1,f'q:ctype:{mid}:fun');before=dict(await n.db.invite(mid));flow=dict(await n.db.flow(1))
    await n.msg(1,'/check');assert dict(await n.db.invite(mid))==before and dict(await n.db.flow(1))==flow
    await n.msg(2,'/check');assert await n.db.flow(2) is None and 'ruxsatini oling' in n.sent(2)[-1]['text']

async def test_check_obeys_disabled_flag(n):
    n.cfg.enable_ceremony=False;await n.msg(1,'/check');flow=await n.db.flow(1)
    assert flow['stage']=='media' and (await n.db.invite(flow['invite_id']))['type']=='fun'

async def test_check_does_not_reset_orphan_draft(n):
    await n.msg(1,'/check');mid=(await n.db.flow(1))['invite_id']
    await n.db.run('DELETE FROM q_flows WHERE uid=?',(1,))
    await n.db.run("UPDATE q_invites SET description='saqlansin' WHERE id=?",(mid,))
    await n.msg(1,'/check')
    assert (await n.db.invite(mid))['description']=='saqlansin' and await n.db.flow(1) is None

async def test_check_preserves_pending_suggestion(n):
    await n.db.run('INSERT INTO q_suggestion_drafts VALUES(?)',(1,))
    await n.msg(1,'/check')
    assert await n.db.one('SELECT uid FROM q_suggestion_drafts WHERE uid=?',(1,)) and await n.db.flow(1) is None
