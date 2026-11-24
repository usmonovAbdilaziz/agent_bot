from test_minimal import n, ready, draft


async def test_admin_report_counts_people_and_published_invitations(n):
    await ready(n)
    await ready(n)
    await draft(n)
    await n.msg(2, '/start')
    await n.msg(2, '/start')
    await n.cb(1, 'q:admin')
    assert 'q:settings' in n.sent(1)[-1]['reply_markup']
    await n.cb(1, 'q:settings')
    text = n.sent(1)[-1]['text']
    assert 'Jami foydalanuvchilar: <b>2</b>' in text
    assert 'Taklifnoma yaratganlar: <b>1</b>' in text
    assert 'Tayyor taklifnomalar: <b>2</b>' in text
    assert 'Faol — 2 kishi' in text
    assert 'Yaratuvchi — 1 kishi' in text
    assert 'Tayyor taklif — 2 ta' in text
    await n.cb(1, 'q:reportusers:0')
    assert '2 ta taklifnoma' in n.sent(1)[-1]['text']
    for action in ('q:settings', 'q:reportusers:0'):
        await n.cb(2, action)
        assert 'Bot hisoboti' not in n.sent(2)[-1]['text']
        assert '2 ta taklifnoma' not in n.sent(2)[-1]['text']
