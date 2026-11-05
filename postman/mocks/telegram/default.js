// Telegram Bot API ning ushbu bot ishlatadigan qismi. Haqiqiy token ishlatmang.
const http = require('http');
let nextId = 100;
let calls = [];
let updates = [];
let failNext = null;
const reply = (res, status, value) => {
  res.writeHead(status, {'Content-Type': 'application/json'});
  res.end(JSON.stringify(value));
};
const server = http.createServer(async (req, res) => {
  const path = req.url.split('?')[0];
  let body = req.body;
  if (!body) {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    body = (req.headers['content-type'] || '').includes('application/json')
      ? JSON.parse(raw || '{}') : Object.fromEntries(new URLSearchParams(raw));
  }
  if (typeof body === 'string') {
    body = (req.headers['content-type'] || '').includes('application/json')
      ? JSON.parse(body || '{}') : Object.fromEntries(new URLSearchParams(body));
  }
  if (path === '/_test/reset') {
    calls = []; updates = []; nextId = 100; failNext = null;
    return reply(res, 200, {ok: true});
  }
  if (path === '/_test/calls') return reply(res, 200, calls);
  if (path === '/_test/rsvp-notices') return reply(res, 200, calls.filter(call => call.method === 'sendMessage' && (call.body.text || '').includes('Taklifga javob')));
  if (path === '/_test/fail-next') {
    failNext = body;
    return reply(res, 200, {ok: true});
  }
  if (path === '/_test/updates') {
    updates.push(...(body.updates || []));
    return reply(res, 200, {ok: true});
  }
  const match = path.match(/^\/bot[^/]+\/([A-Za-z]+)$/);
  if (!match) return reply(res, 501, {ok: false, error_code: 501, description: 'Endpoint not modeled'});
  const method = match[1];
  calls.push({method, body});
  const chat = Number(body.chat_id);
  if (failNext && method === failNext.method && chat === Number(failNext.chat_id)) {
    const code = Number(failNext.code); failNext = null;
    return reply(res, code, {ok:false, error_code:code, description:code===403?'Forbidden: bot was blocked':'Internal Server Error'});
  }
  if (chat === 403) return reply(res, 403, {ok: false, error_code: 403, description: 'Forbidden: bot was blocked by the user'});
  if (chat === 500) return reply(res, 500, {ok: false, error_code: 500, description: 'Internal Server Error'});
  let result;
  if (method === 'getMe') result = {id: 123456, is_bot: true, first_name: 'Sinov', username: 'test_agent_bot'};
  else if (['answerCallbackQuery','setMyCommands','deleteWebhook','setChatMenuButton'].includes(method)) result = true;
  else if (method === 'getUpdates') {
    result = updates.filter(u => u.update_id >= Number(body.offset || 0));
    if (!result.length) await new Promise(resolve => setTimeout(resolve, 50));
  }
  else if (['sendMessage','sendPhoto','sendVideo','sendVideoNote','copyMessage','editMessageReplyMarkup'].includes(method)) {
    if (!chat || (method === 'sendMessage' && !body.text) ||
        (method === 'sendPhoto' && !body.photo) ||
        (method === 'copyMessage' && (!body.message_id || !body.from_chat_id))) {
      return reply(res, 400, {ok: false, error_code: 400, description: 'Bad Request: missing required fields'});
    }
    result = {message_id: ++nextId};
    if (method !== 'copyMessage') Object.assign(result, {date: Math.floor(Date.now()/1000), chat: {id: chat, type: 'private'}});
  } else return reply(res, 501, {ok: false, error_code: 501, description: 'Endpoint not modeled'});
  reply(res, 200, {ok: true, result});
});
server.listen(process.env.PORT || 4617);
