import React, { useCallback, useEffect, useRef, useState } from 'react';
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

function useFireworks(active) {
  useEffect(() => {
    if (!active || matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    const canvas = document.getElementById('fireworks');
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;
    const width = innerWidth;
    const height = innerHeight;
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.scale(ratio, ratio);
    const colors = ['#1769c2', '#db4770', '#d49716', '#21836c'];
    const particles = [];
    for (let burst = 0; burst < 3; burst += 1) {
      const x = width * [0.24, 0.75, 0.5][burst];
      const y = height * [0.3, 0.4, 0.22][burst];
      for (let index = 0; index < 42; index += 1) {
        const angle = (Math.PI * 2 * index) / 42;
        const speed = 75 + Math.random() * 100;
        particles.push({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, color: colors[index % colors.length], delay: burst * 0.35 });
      }
    }
    const started = performance.now();
    let frameId;
    function draw(now) {
      const time = (now - started) / 1_000;
      context.clearRect(0, 0, width, height);
      particles.forEach(particle => {
        const age = time - particle.delay;
        if (age < 0 || age > 1.7) return;
        context.globalAlpha = Math.max(0, 1 - age / 1.7);
        context.fillStyle = particle.color;
        context.beginPath();
        context.arc(particle.x + particle.vx * age, particle.y + particle.vy * age + 65 * age * age, 2.5, 0, Math.PI * 2);
        context.fill();
      });
      if (time < 2.5) frameId = requestAnimationFrame(draw);
      else context.clearRect(0, 0, width, height);
    }
    frameId = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frameId);
      context.clearRect(0, 0, width, height);
    };
  }, [active]);
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

function ChoiceArena({ disabled, onAccept, onEvasion }) {
  const arenaRef = useRef(null);
  const yesRef = useRef(null);
  const noRef = useRef(null);
  const [position, setPosition] = useState(null);

  const evade = useCallback(event => {
    event.preventDefault();
    const arena = arenaRef.current;
    const yes = yesRef.current;
    const no = noRef.current;
    if (disabled || !arena || !yes || !no) return;
    onEvasion();
    const maxX = Math.max(0, arena.clientWidth - no.offsetWidth);
    const maxY = Math.max(0, arena.clientHeight - no.offsetHeight);
    const positions = [[0, 1], [1, 1], [0.5, 0.6], [0, 0.55], [1, 0.55], [1, 0]];
    const options = positions
      .map(([x, y]) => [x * maxX, y * maxY])
      .filter(([x, y]) => {
        const overlap = x < yes.offsetLeft + yes.offsetWidth + 12
          && x + no.offsetWidth > yes.offsetLeft - 12
          && y < yes.offsetTop + yes.offsetHeight + 12
          && y + no.offsetHeight > yes.offsetTop - 12;
        return !overlap && Math.hypot(x - no.offsetLeft, y - no.offsetTop) > 30;
      });
    const [left, top] = options[Math.floor(Math.random() * options.length)] || [maxX, maxY];
    setPosition({ left, top });
    tg?.HapticFeedback?.impactOccurred('light');
  }, [disabled, onEvasion]);

  return (
    <div className="arena" ref={arenaRef}>
      <button ref={yesRef} className="primary yes" type="button" onClick={onAccept} disabled={disabled}>Ha</button>
      <button
        ref={noRef}
        className="no"
        type="button"
        style={position || undefined}
        onPointerEnter={event => { if (event.pointerType === 'mouse') evade(event); }}
        onPointerDown={evade}
        onClick={event => { if (event.detail === 0) evade(event); else event.preventDefault(); }}
        disabled={disabled}
        aria-label="Yo‘q — qochadigan hazil tugmasi"
      >Yo‘q</button>
    </div>
  );
}

function Success({ celebrate }) {
  const [showClose, setShowClose] = useState(false);
  useFireworks(celebrate);
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

function Invitation({ invite, onStatus, accepted }) {
  const [attempts, increment] = useAttemptCounter(invite.id);
  const [sticker, setSticker] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const stickerTimer = useRef(null);

  useEffect(() => () => clearTimeout(stickerTimer.current), []);

  const onEvasion = useCallback(() => {
    const value = increment();
    if (value % 10 === 0) {
      setSticker(true);
      clearTimeout(stickerTimer.current);
      stickerTimer.current = setTimeout(() => setSticker(false), 1_400);
    }
  }, [increment]);

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
    <section className={`invitation design-${DESIGNS[invite.design]?.type === (invite.type || 'fun') ? invite.design : 'classic'} position-${['top', 'center', 'bottom'].includes(invite.details?.layout?.text_position) ? invite.details.layout.text_position : 'bottom'}`}>
      <BackgroundMedia invite={invite} onError={message => onStatus(message, true)} />
      <div className="scrim" aria-hidden="true" />
      <div className="invitation-content">
        <div className="text-panel" tabIndex="0">
          <h1>{invite.title}</h1>
          <p className="description">{invite.description}</p>
        </div>
        <ChoiceArena disabled={accepting || invite.preview} onAccept={accept} onEvasion={onEvasion} />
        <p className={`preview-note${invite.preview ? '' : ' preview-placeholder'}`} aria-hidden={!invite.preview}>Oluvchiga shunday ko‘rinadi. Tasdiqlash uchun botga qayting.</p>
      </div>
      <div className="sticker" hidden={!sticker} role="img" aria-label="Jahli chiqqan stiker">😡</div>
    </section>
  );
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
      {screen === 'ready' && invite && <Invitation invite={invite} onStatus={showStatus} accepted={() => setScreen('accepted')} />}
      {screen === 'accepted' && <Success celebrate={invite?.status !== 'accepted'} />}
    </>
  );
}

createRoot(document.getElementById('app')).render(<App />);
