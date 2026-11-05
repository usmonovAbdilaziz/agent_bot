import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import { DESIGNS } from './designs';

const tg = window.Telegram?.WebApp;

function messageFor(error) {
  if (error?.name === 'AbortError' || error instanceof TypeError) {
    return 'Aloqa uzildi. Qayta urinib ko‘ring.';
  }
  return error?.message || 'Taklif yuklanmadi. Qayta urinib ko‘ring.';
}

async function api(path, { method = 'GET', json, blob = false } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), blob ? 60_000 : 20_000);
  try {
    const headers = { 'X-Telegram-Init-Data': tg?.initData || '' };
    if (json !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(new URL(`api${path}`, document.baseURI), {
      method,
      signal: controller.signal,
      headers,
      body: json === undefined ? undefined : JSON.stringify(json)
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || 'Taklif yuklanmadi. Qayta urinib ko‘ring.');
    }
    return blob ? response.blob() : response.json();
  } finally {
    clearTimeout(timer);
  }
}

function useAttemptCounter(id) {
  const key = `qadam:no:${tg?.initDataUnsafe?.user?.id || 'receiver'}:${id}`;
  const [value, setValue] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      return Number.isInteger(saved) && saved >= 0 && saved <= 1_000_000 ? saved : 0;
    } catch {
      return 0;
    }
  });
  const valueRef = useRef(value);
  const increment = useCallback(() => {
    const next = Math.min(valueRef.current + 1, 1_000_000);
    valueRef.current = next;
    try { localStorage.setItem(key, String(next)); } catch { /* WebView storage can be unavailable. */ }
    setValue(next);
    return next;
  }, [key]);
  return [value, increment];
}

function useCelebration(effectKey, active) {
  useEffect(() => {
    if (!active || matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    const canvas = document.getElementById('fireworks');
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;
    const width = innerWidth, height = innerHeight;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = width * ratio; canvas.height = height * ratio;
    context.scale(ratio, ratio);
    const palette = effectKey === 'neon-glow' ? ['#00efff', '#fa42e9', '#b3ff7a'] : ['#ff7c9d', '#ffcb52', '#9ad9ff', '#c9a3ff'];
    const count = effectKey === 'balloons' ? 60 : 80;
    const particles = Array.from({ length: count }, (_, i) => ({
      x: Math.random() * width, y: Math.random() * height,
      speed: 25 + Math.random() * 65, size: 3 + Math.random() * 5,
      color: palette[i % palette.length], phase: Math.random() * 6.28
    }));
    const start = performance.now(); let frame;
    function draw(now) {
      const t = (now - start) / 1000;
      context.clearRect(0, 0, width, height);
      particles.forEach((p, i) => {
        const snow = effectKey === 'snow';
        const rise = effectKey === 'hearts' || effectKey === 'balloons';
        const y = (p.y + (rise ? -1 : 1) * p.speed * t + height * 3) % height;
        const x = p.x + Math.sin(t * 2 + p.phase) * 12;
        context.globalAlpha = Math.min(1, Math.max(0, 2.5 - t));
        context.fillStyle = snow ? '#ffffff' : p.color;
        context.shadowColor = p.color; context.shadowBlur = effectKey === 'neon-glow' ? 15 : 0;
        if (effectKey === 'hearts') {
          context.font = `${p.size * 3}px sans-serif`; context.fillText('♥', x, y);
        } else if (effectKey === 'balloons' && i % 3 !== 0) {
          context.beginPath(); context.ellipse(x, y, p.size, p.size * 1.35, 0, 0, Math.PI * 2); context.fill();
          context.strokeStyle = p.color; context.beginPath(); context.moveTo(x, y + p.size); context.lineTo(x, y + p.size * 3); context.stroke();
        } else if (snow || effectKey === 'neon-glow') {
          context.beginPath(); context.arc(x, y, snow ? p.size / 2 : p.size, 0, Math.PI * 2); context.fill();
        } else context.fillRect(x, y, p.size * 1.3, p.size / 1.8);
      });
      if (t < 2.5) frame = requestAnimationFrame(draw);
      else context.clearRect(0, 0, width, height);
    }
    frame = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(frame); context.clearRect(0, 0, width, height); };
  }, [effectKey, active]);
}

function BackgroundMedia({ invite, onError }) {
  const [state, setState] = useState({ status: invite.media_kind === 'none' ? 'empty' : 'loading' });
  const [muted, setMuted] = useState(true);
  const videoRef = useRef(null);
  const urlRef = useRef(null);

  const load = useCallback(async () => {
    if (invite.media_kind === 'none') return;
    setState({ status: 'loading' });
    try {
      const data = await api(`/invites/${invite.id}/media`, { blob: true });
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      const url = URL.createObjectURL(data);
      urlRef.current = url;
      setState({ status: 'ready', url });
    } catch (error) {
      setState({ status: 'error', message: messageFor(error) });
    }
  }, [invite.id, invite.media_kind]);

  useEffect(() => {
    load();
    return () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    };
  }, [load]);

  const failed = useCallback(() => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
    setState({ status: 'error', message: 'Media ochilmadi.' });
    onError('Media ochilmadi.');
  }, [onError]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || state.status !== 'ready') return undefined;
    video.play().catch(() => undefined);
    return undefined;
  }, [state.status]);

  if (state.status === 'empty') return null;
  if (state.status === 'loading') return <p className="media-note media-control">Media yuklanmoqda…</p>;
  if (state.status === 'error') {
    return <div className="media-control"><p className="media-note">{state.message}</p><button type="button" onClick={load}>Qayta yuklash</button></div>;
  }
  if (invite.media_kind === 'photo') {
    return <img className="media" src={state.url} alt="" onError={failed} />;
  }
  const toggleSound = () => {
    const video = videoRef.current;
    if (!video) return;
    const next = !muted;
    video.muted = next;
    setMuted(next);
    video.play().catch(() => onError('Videoni ijro etib bo‘lmadi.'));
  };
  return (
    <>
      <video ref={videoRef} className="media" src={state.url} muted={muted} autoPlay loop playsInline aria-label="Taklif videosi" onError={failed} />
      <button className="sound media-control" type="button" onClick={toggleSound} aria-pressed={String(!muted)}>
        {muted ? 'Ovozni yoqish' : 'Ovozni o‘chirish'}
      </button>
    </>
  );
}

function ChoiceArena({ disabled, onAccept, onEvasion, attempts, behavior, design }) {
  const arenaRef = useRef(null);
  const yesRef = useRef(null);
  const noRef = useRef(null);
  const [position, setPosition] = useState(null);
  const scale = 1 + Math.min(attempts * 0.04, 0.8);
  const phrase = attempts >= behavior.phrase_at
    ? behavior.phrases[(attempts - behavior.phrase_at) % behavior.phrases.length] : 'Yo‘q';

  const reposition = useCallback(() => {
    const arena = arenaRef.current, yes = yesRef.current, no = noRef.current;
    if (!arena || !yes || !no) return;
    const maxX = Math.max(0, arena.clientWidth - no.offsetWidth);
    const maxY = Math.max(0, arena.clientHeight - no.offsetHeight);
    const minY = Math.min(maxY, yes.offsetTop + yes.offsetHeight + 12);
    const options = [[0, maxY], [maxX, maxY], [maxX / 2, minY], [0, minY], [maxX, minY]]
      .filter(([x, y]) => !(x < yes.offsetLeft + yes.offsetWidth + 8 && x + no.offsetWidth > yes.offsetLeft - 8 && y < yes.offsetTop + yes.offsetHeight + 8));
    setPosition(previous => {
      if (!options.length) return { left: maxX, top: maxY };
      const choices = options.filter(([x, y]) => !previous || Math.hypot(x - previous.left, y - previous.top) > 30);
      const pool = choices.length ? choices : options;
      const [left, top] = pool[attempts % pool.length];
      return { left, top };
    });
  }, [attempts]);
  useLayoutEffect(() => { reposition(); }, [reposition, phrase]);
  useEffect(() => { window.addEventListener('resize', reposition); return () => window.removeEventListener('resize', reposition); }, [reposition]);

  const evade = useCallback(event => {
    event.preventDefault();
    if (disabled) return;
    onEvasion();
    tg?.HapticFeedback?.impactOccurred('light');
  }, [disabled, onEvasion]);

  return (
    <div className={`arena${attempts >= behavior.strong_at ? ` strong-reaction strong-${attempts % 2 ? 'odd' : 'even'}` : ''}`} ref={arenaRef}>
      <button ref={yesRef} className="primary yes" type="button" style={{width: `${104 * scale}px`, height: `${48 * scale}px`}} onClick={onAccept} disabled={disabled}>Ha</button>
      <button ref={noRef} className={`no${design === 'neon' && attempts ? ` glitch glitch-${attempts % 2 ? 'odd' : 'even'}` : ''}`} type="button" style={position || undefined}
        onPointerEnter={event => { if (event.pointerType === 'mouse') evade(event); }}
        onPointerDown={evade}
        onClick={event => { if (event.detail === 0) evade(event); else event.preventDefault(); }}
        disabled={disabled} aria-label="Yo‘q — qochadigan hazil tugmasi">{phrase}</button>
    </div>
  );
}

function Success({ celebrate, effect }) {
  const [showClose, setShowClose] = useState(false);
  useCelebration(effect, celebrate);
  useEffect(() => {
    const closeTimer = setTimeout(() => tg?.close(), celebrate ? 2_800 : 1_200);
    const buttonTimer = setTimeout(() => setShowClose(true), 4_000);
    return () => { clearTimeout(closeTimer); clearTimeout(buttonTimer); };
  }, [celebrate]);
  return (
    <section className="success">
      <h1>Tanlovingiz uchun rahmat!</h1>
      <p>{showClose ? 'Javobingiz qabul qilindi.' : 'Sahifa yopilmoqda…'}</p>
      {showClose && <button className="close" type="button" onClick={() => tg?.close()}>Sahifani yopish</button>}
    </section>
  );
}

function FunInvitation({ invite, onStatus, accepted }) {
  const design = DESIGNS[invite.design]?.type === (invite.type || 'fun') ? DESIGNS[invite.design] : DESIGNS.classic;
  const behavior = design.behavior;
  const [attempts, increment] = useAttemptCounter(invite.id);
  const [sticker, setSticker] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const stickerTimer = useRef(null);

  useEffect(() => () => clearTimeout(stickerTimer.current), []);

  const onEvasion = useCallback(() => {
    const value = increment();
    if (value > 0 && value % behavior.sticker_at === 0) {
      setSticker(true);
      clearTimeout(stickerTimer.current);
      stickerTimer.current = setTimeout(() => setSticker(false), 1_400);
    }
  }, [increment, behavior.sticker_at]);

  const accept = async () => {
    if (accepting || invite.preview) return;
    setAccepting(true);
    onStatus('');
    try {
      await api(`/invites/${invite.id}/accept`, { method: 'POST', json: { no_attempts: attempts } });
      tg?.HapticFeedback?.notificationOccurred('success');
      accepted(true);
    } catch (error) {
      onStatus(messageFor(error), true);
      setAccepting(false);
    }
  };

  return (
    <section className={`invitation design-${design.id} position-${['top', 'center', 'bottom'].includes(invite.details?.layout?.text_position) ? invite.details.layout.text_position : 'bottom'}`}>
      <BackgroundMedia invite={invite} onError={message => onStatus(message, true)} />
      <div className="scrim" aria-hidden="true" />
      <div className={`invitation-content${attempts >= behavior.strong_at ? ` reaction-${attempts % 2 ? 'odd' : 'even'}` : ''}`}>
        <div className="text-panel" tabIndex="0">
          <h1>{invite.title}</h1>
          <p className="description">{invite.description}</p>
        </div>
        <ChoiceArena disabled={accepting || invite.preview} onAccept={accept} onEvasion={onEvasion} attempts={attempts} behavior={behavior} design={design.id} />
        <p className={`preview-note${invite.preview ? '' : ' preview-placeholder'}`} aria-hidden={!invite.preview}>Oluvchiga shunday ko‘rinadi. Tasdiqlash uchun botga qayting.</p>
      </div>
      <div className="sticker" hidden={!sticker} role="img" aria-label="Jahli chiqqan stiker">😡</div>
    </section>
  );
}

const CEREMONY_NAMES = { wedding: 'To‘y', nikah: 'Nikoh', beshik: 'Beshik to‘y', sunnat: 'Sunnat to‘y', fotiha: 'Fotiha', birthday: 'Tug‘ilgan kun', other: 'Boshqa' };
const MONTHS = ['yanvar','fevral','mart','aprel','may','iyun','iyul','avgust','sentabr','oktabr','noyabr','dekabr'];
const DAYS = ['yakshanba','dushanba','seshanba','chorshanba','payshanba','juma','shanba'];
const MAP_HOSTS = new Set(['maps.google.com','maps.google.co.uz','maps.app.goo.gl','goo.gl','yandex.uz','yandex.ru','yandex.com','maps.yandex.ru','maps.yandex.com','2gis.uz','2gis.ru','2gis.com','go.2gis.com']);
function safeMapURL(value) {
  if (typeof value !== 'string' || !value || value.length > 500 || /[\s\x00-\x1f]/.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || !MAP_HOSTS.has(url.hostname) || url.username || url.password || (url.port && url.port !== '443')) return null;
    if (['yandex.uz','yandex.ru','yandex.com'].includes(url.hostname) && !url.pathname.startsWith('/maps')) return null;
    if (url.hostname === 'goo.gl' && !url.pathname.startsWith('/maps/')) return null;
    return url.href;
  } catch { return null; }
}
function ceremonyDate(date) {
  const [day, month, year] = date.split('.').map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${DAYS[weekday]}, ${day}-${MONTHS[month - 1]} ${year}`;
}
function calendarURL(invite) {
  const d = invite.details;
  const [day, month, year] = d.date.split('.').map(Number);
  const [hour, minute] = d.time.split(':').map(Number);
  const start = new Date(Date.UTC(year, month - 1, day, hour, minute));
  const end = new Date(start.getTime() + 3 * 60 * 60 * 1000);
  const local = value => value.toISOString().replace(/[-:]/g,'').replace('.000Z','');
  const params = new URLSearchParams({ action:'TEMPLATE', text:invite.title, dates:`${local(start)}/${local(end)}`,
    ctz:'Asia/Tashkent', location:d.address, details:d.note || '' });
  return `https://calendar.google.com/calendar/render?${params}`;
}
function CeremonyInvitation({ invite, onStatus }) {
  const details = invite.details;
  const design = DESIGNS[invite.design]?.type === 'ceremony' ? invite.design : 'nafis';
  const [opening, setOpening] = useState(() => design === 'envelope' && !matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    if (!opening) return undefined;
    const timer = setTimeout(() => setOpening(false), 1350);
    return () => clearTimeout(timer);
  }, [opening]);
  const position = ['top', 'center', 'bottom'].includes(details?.layout?.text_position) ? details.layout.text_position : 'bottom';
  const [selection, setSelection] = useState(null);
  const [guests, setGuests] = useState(1);
  const [response, setResponse] = useState(invite.rsvp || null);
  const [submitted, setSubmitted] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const map = safeMapURL(details.map_url);
  const openLink = url => {
    if (tg?.openLink) tg.openLink(url);
    else setError('Havolani ochib bo‘lmadi. Telegram orqali qayta oching.');
  };
  const submit = async () => {
    if (pending || selection === null || invite.preview) return;
    setPending(true); setError('');
    try {
      const result = await api(`/invites/${invite.id}/rsvp`, { method:'POST', json:{ attending:selection, guests:selection ? guests : 0 } });
      setResponse(result.rsvp); setSubmitted(true);
    } catch (err) { setError(messageFor(err)); }
    finally { setPending(false); }
  };
  return <section className={`invitation ceremony ceremony-${design} position-${position}`}>
    {opening && <button className="envelope-intro" type="button" autoFocus onClick={() => setOpening(false)} aria-label="Konvertni ochish, animatsiyani o‘tkazib yuborish"><span className="envelope-shape" aria-hidden="true"><span className="envelope-flap" /><span className="envelope-seal">✦</span></span><span>Taklifni ochish</span></button>}
    <BackgroundMedia invite={invite} onError={message => onStatus(message, true)} />
    <div className="scrim" aria-hidden="true" />
    {!opening && <div className="invitation-content"><div className="text-panel ceremony-panel" tabIndex="0">
      <h1>{invite.title}</h1>
      <div className="ceremony-cards">
        <section className="ceremony-card"><h2>Marosim</h2><p>{CEREMONY_NAMES[details.event_kind] || details.event_kind}</p></section>
        <section className="ceremony-card ceremony-date"><h2>Sana va vaqt</h2><p>{design === 'ticket' ? <><span>{ceremonyDate(details.date)}</span><span>{details.time}</span></> : <>{ceremonyDate(details.date)} · {details.time}</>}</p></section>
        <section className="ceremony-card"><h2>Manzil</h2><p>{details.address}</p></section>
        {details.program?.length > 0 && <section className="ceremony-card"><h2>Dastur</h2><ul>{details.program.map((line,index)=><li key={index}>{line}</li>)}</ul></section>}
        {details.note && <section className="ceremony-card"><h2>Qo‘shimcha ma’lumot</h2><p className="description">{details.note}</p></section>}
      </div>
      <div className="ceremony-links">
        {map && <button type="button" onClick={()=>openLink(map)}>Xaritada ochish</button>}
        <button type="button" onClick={()=>openLink(calendarURL(invite))}>Taqvimga qo‘shish</button>
      </div>
      <section className="rsvp" aria-labelledby="rsvp-title">
        {response ? <>
          <h2 id="rsvp-title">{submitted ? 'Javobingiz uchun rahmat!' : 'Siz javob bergansiz'}</h2>
          <p>{response.attending ? `Kelaman · ${response.guests} mehmon` : 'Kela olmayman'}</p>
          <button type="button" onClick={()=>tg?.close()}>Telegramga qaytish</button>
        </> : invite.rsvp_closed ? <h2 id="rsvp-title">Marosim o‘tib ketgan</h2> : <>
          <h2 id="rsvp-title">Tashrifingizni tasdiqlang</h2>
          {invite.preview && <p>Bu ko‘rib chiqish. Javobni oluvchi yuboradi.</p>}
          <div className="rsvp-options">
            <button type="button" aria-pressed={selection===1} disabled={pending || invite.preview} onClick={()=>setSelection(1)}>Kelaman</button>
            <button type="button" aria-pressed={selection===0} disabled={pending || invite.preview} onClick={()=>setSelection(0)}>Kela olmayman</button>
          </div>
          {selection===1 && <div className="guest-stepper"><span>Mehmonlar soni</span><div>
            <button type="button" aria-label="Mehmonni kamaytirish" disabled={guests<=1 || pending} onClick={()=>setGuests(n=>n-1)}>−</button>
            <output aria-live="polite">{guests}</output>
            <button type="button" aria-label="Mehmonni qo‘shish" disabled={guests>=10 || pending} onClick={()=>setGuests(n=>n+1)}>+</button>
          </div></div>}
          <button className="rsvp-submit" type="button" disabled={selection===null || pending || invite.preview} onClick={submit}>{pending?'Yuborilmoqda…':'Javobni yuborish'}</button>
        </>}
        {error && <p role="alert" className="rsvp-error">{error}</p>}
      </section>
    </div></div>}
  </section>;
}

function App() {
  const id = new URLSearchParams(location.search).get('invite');
  const [screen, setScreen] = useState('loading');
  const [invite, setInvite] = useState(null);
  const [status, setStatus] = useState({ text: 'Taklif ochilmoqda…', error: false });
  const loadedId = useRef(null);

  const showStatus = useCallback((text = '', error = false) => setStatus({ text, error }), []);
  const load = useCallback(async () => {
    if (!tg?.initData || !id || !/^\d+$/.test(id)) {
      setScreen('ready');
      showStatus('Taklifni botdagi “Taklifni ochish” tugmasi orqali oching.');
      return;
    }
    setScreen('loading');
    showStatus('Taklif ochilmoqda…');
    try {
      const data = await api(`/invites/${id}`);
      setInvite(data);
      showStatus('');
      setScreen(data.status === 'accepted' && !data.preview ? 'accepted' : 'ready');
    } catch (error) {
      setScreen('error');
      showStatus(messageFor(error), true);
    }
  }, [id, showStatus]);

  useEffect(() => {
    tg?.ready();
    tg?.expand();
    if (loadedId.current !== id) {
      loadedId.current = id;
      load();
    }
  }, [id, load]);

  useEffect(() => {
    document.getElementById('app')?.setAttribute('aria-busy', String(screen === 'loading'));
  }, [screen]);

  return (
    <>
      {status.text && <p id="status" role="status" className={status.error ? 'error' : ''}>{status.text}</p>}
      {screen === 'loading' && <div className="loading-card" aria-hidden="true"><span /><span /><span /></div>}
      {screen === 'error' && <button type="button" className="retry" onClick={load}>Qayta urinish</button>}
      {screen === 'ready' && invite && (invite.type === 'ceremony'
        ? <CeremonyInvitation invite={invite} onStatus={showStatus} />
        : <FunInvitation invite={invite} onStatus={showStatus} accepted={() => setScreen('accepted')} />)}
      {screen === 'accepted' && <Success celebrate={invite?.status !== 'accepted'} effect={DESIGNS[invite?.design]?.effect || DESIGNS.classic.effect} />}
    </>
  );
}

createRoot(document.getElementById('app')).render(<App />);
