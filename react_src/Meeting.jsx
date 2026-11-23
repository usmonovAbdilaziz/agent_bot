import React, { useEffect, useLayoutEffect, useId, useRef, useState } from 'react';
import plans from './meeting-data.json';
import MeetingDateTime from './MeetingDateTime';
import './meeting.css';

const tg = window.Telegram?.WebApp;
const phases = ['intro', 'question', 'celebrate', 'when', 'plan'];
const months = ['yanvar','fevral','mart','aprel','may','iyun','iyul','avgust','sentabr','oktabr','noyabr','dekabr'];
const weekdays = ['Yakshanba','Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba'];
function uzDate(value) { return new Date(Date.parse(value) + 5 * 3600_000); }
function dateLabel(value) {
  const d = uzDate(value);
  const year = d.getUTCFullYear() === uzDate(new Date().toISOString()).getUTCFullYear() ? '' : ` ${d.getUTCFullYear()}`;
  return `${d.getUTCDate()}-${months[d.getUTCMonth()]}${year}, ${weekdays[d.getUTCDay()]}`;
}
function timeLabel(value) { const d = uzDate(value); return `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`; }

function Icon({ kind = 'heart', ...props }) {
  const paths = {
    heart: 'M12 20s-8-4.8-8-10a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.2-8 10-8 10Z',
    calendar: 'M5 5h14v15H5ZM8 3v4m8-4v4M5 10h14M8 13h2m3 0h3m-8 3h2',
    clock: 'M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
    coffee: 'M4 8h12v6a5 5 0 0 1-10 0V8m10 1h2a3 3 0 0 1 0 6h-2M4 21h15M7 3v2m5-2v2',
    film: 'M4 4h16v16H4ZM8 4v16m8-16v16M4 9h4m-4 6h4m8-6h4m-4 6h4',
    dinner: 'M6 3v7m-3-7v5a3 3 0 0 0 6 0V3M6 11v10M17 3c-3 4-3 8 1 8v10m0-18v8',
    spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4',
    game: 'M7 8h10l4 9a2 2 0 0 1-3 2l-4-3h-4l-4 3a2 2 0 0 1-3-2ZM7 10v4m-2-2h4m6-1h.1m2 2h.1',
    download: 'M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6',
    arrow: 'M4 12h16m-6-6 6 6-6 6',
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[kind] || paths.heart} /></svg>;
}

function JoinedHeart({ progress = 100 }) {
  const id = useId().replaceAll(':', '');
  const gap = (1 - progress / 100) * 8;
  const d = 'M40 69C32 61 8 44 8 26C8 9 29 4 40 19C51 4 72 9 72 26C72 44 48 61 40 69Z';
  return <svg className="meeting-heart" viewBox="-8 0 96 80" aria-hidden="true">
    <defs><clipPath id={`${id}left`}><polygon points="0,0 41,0 36,26 45,36 36,46 42,56 40,80 0,80" /></clipPath><clipPath id={`${id}right`}><polygon points="41,0 80,0 80,80 40,80 42,56 36,46 45,36 36,26" /></clipPath></defs>
    <g transform={`translate(${-gap} 0)`}><path d={d} clipPath={`url(#${id}left)`} /></g>
    <g transform={`translate(${gap} 0)`}><path d={d} clipPath={`url(#${id}right)`} /></g>
  </svg>;
}

function Choice({ onYes, onNo, attempts }) {
  const [position, setPosition] = useState(null);
  const arena = useRef(null);
  const yes = useRef(null);
  const no = useRef(null);
  const content = useRef(null);
  const pointer = useRef(null);
  const last = useRef(null);
  const hintId = useId();
  const hint = ['Yana bir bor o‘ylab ko‘rasizmi?', 'Birga yaxshi vaqt o‘tkazamiz.', 'Ha desangiz, rejani tanlaymiz.'][Math.max(0, attempts - 1) % 3];

  useLayoutEffect(() => {
    function relocate() {
      const bounds = arena.current.getBoundingClientRect();
      const primary = yes.current.getBoundingClientRect();
      const label = content.current.getBoundingClientRect();
      const chip = no.current.getBoundingClientRect();
      const radius = primary.height / 2;
      const straight = Math.max(0, primary.width - primary.height);
      const arc = Math.PI * radius;
      const perimeter = 2 * (straight + arc);
      const candidates = [];
      // Sample the pill's actual outline; keep the heart/Ha label and pointer clear.
      for (let i = 0; i < 64; i++) {
        const distance = i / 64 * perimeter;
        let x, y, nx, ny;
        if (distance < straight) {
          x = primary.left + radius + distance; y = primary.top; nx = 0; ny = -1;
        } else if (distance < straight + arc) {
          const angle = -Math.PI / 2 + (distance - straight) / radius;
          nx = Math.cos(angle); ny = Math.sin(angle);
          x = primary.right - radius + radius * nx; y = primary.top + radius + radius * ny;
        } else if (distance < 2 * straight + arc) {
          x = primary.right - radius - (distance - straight - arc); y = primary.bottom; nx = 0; ny = 1;
        } else {
          const angle = Math.PI / 2 + (distance - 2 * straight - arc) / radius;
          nx = Math.cos(angle); ny = Math.sin(angle);
          x = primary.left + radius + radius * nx; y = primary.top + radius + radius * ny;
        }
        const left = Math.max(bounds.left + 4, Math.min(bounds.right - chip.width - 4, x + nx * 12 - chip.width / 2));
        const top = Math.max(bounds.top + 4, Math.min(bounds.bottom - chip.height - 4, y + ny * 12 - chip.height / 2));
        const right = left + chip.width, bottom = top + chip.height;
        if (left < label.right + 10 && right > label.left - 10 && top < label.bottom + 10 && bottom > label.top - 10) continue;
        if (pointer.current && pointer.current.x > left - 14 && pointer.current.x < right + 14 && pointer.current.y > top - 14 && pointer.current.y < bottom + 14) continue;
        candidates.push({ left: left - bounds.left, top: top - bounds.top });
      }
      const distant = candidates.filter(point => !last.current || Math.hypot(point.left - last.current.left, point.top - last.current.top) > 40);
      const options = distant.length ? distant : candidates;
      if (!options.length) return;
      const next = options[Math.floor(Math.random() * options.length)];
      last.current = next;
      setPosition(next);
    }
    relocate();
    let initialObservation = true;
    const observer = new ResizeObserver(() => {
      if (initialObservation) { initialObservation = false; return; }
      relocate();
    });
    observer.observe(arena.current); observer.observe(yes.current); observer.observe(no.current);
    const timer = window.setInterval(() => {
      if (document.hidden || window.matchMedia('(prefers-reduced-motion: reduce)').matches
          || document.activeElement === no.current || document.activeElement === yes.current) return;
      relocate();
    }, 1800);
    return () => { observer.disconnect(); window.clearInterval(timer); };
  }, [attempts]);

  function evade(event) {
    event.preventDefault();
    if (event.type.startsWith('pointer')) pointer.current = { x: event.clientX, y: event.clientY };
    onNo();
    tg?.HapticFeedback?.impactOccurred('light');
  }
  return <div className="meeting-choices" ref={arena} style={{ '--yes-growth': Math.min(attempts, 8) }}
    onPointerMove={event => { pointer.current = { x: event.clientX, y: event.clientY }; }} onPointerLeave={() => { pointer.current = null; }}>
    <button ref={yes} type="button" className="meeting-action yes" onClick={onYes}><span ref={content} className="meeting-yes-content"><Icon /> Ha</span></button>
    <button ref={no} type="button" className="meeting-no" style={position || undefined}
      onPointerEnter={event => { if (event.pointerType === 'mouse') evade(event); }}
      onPointerDown={evade} onClick={event => { if (event.detail === 0) evade(event); else event.preventDefault(); }}
      aria-label="Yo‘q — qochadigan hazil tugmasi" aria-describedby={attempts ? hintId : undefined}>Yo‘q</button>
    {attempts > 0 && <p id={hintId} className="meeting-hint" role="status">{hint}</p>}
  </div>;
}

function DateSummary({ when }) {
  return <div className="meeting-date-summary"><Icon kind="calendar" /><span>{dateLabel(when)}<small>{timeLabel(when)} · O‘zbekiston vaqti</small></span></div>;
}

export default function Meeting({ invite, api, onStatus, renderMedia }) {
  const config = invite.details || {};
  const recipient = config.meeting_recipient || invite.title;
  const sender = config.meeting_sender || '';
  const key = `qadam:meeting:${tg?.initDataUnsafe?.user?.id || 'receiver'}:${invite.id}:${invite.preview ? 'preview' : 'reply'}`;
  const [draft, setDraft] = useState(() => {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(key)); } catch { /* optional storage */ }
    return {
      phase: phases.includes(saved?.phase) ? saved.phase : 'intro',
      when: typeof saved?.when === 'string' && saved.when.length < 40 ? saved.when : '',
      customDate: typeof saved?.customDate === 'string' ? saved.customDate.slice(0, 10) : '',
      customTime: typeof saved?.customTime === 'string' ? saved.customTime.slice(0, 5) : '',
      choice: typeof saved?.choice === 'string' ? saved.choice : '',
      plan: plans.some(p => p.id === saved?.plan) ? saved.plan : '',
      note: typeof saved?.note === 'string' ? saved.note.slice(0, 300) : '',
      attempts: Number.isInteger(saved?.attempts) && saved.attempts >= 0 ? Math.min(saved.attempts, 1_000_000) : 0,
    };
  });
  const [progress, setProgress] = useState(draft.phase === 'intro' ? 0 : 100);
  const [receipt, setReceipt] = useState(config.meeting_response || null);
  const [complete, setComplete] = useState(invite.status === 'accepted');
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const heading = useRef(null);
  const busy = useRef(false);
  const exportBusy = useRef(false);
  const attempts = useRef(draft.attempts);
  const slots = (config.meeting_slots || []).filter(value => Number.isFinite(Date.parse(value)) && Date.parse(value) > Date.now());
  const customWhen = draft.customDate && draft.customTime ? `${draft.customDate}T${draft.customTime}+05:00` : '';
  const customChoice = draft.choice === 'custom' || slots.length === 0;
  const selectedWhen = customChoice ? customWhen : draft.when;
  const validWhen = Number.isFinite(Date.parse(selectedWhen)) && Date.parse(selectedWhen) > Date.now() && Date.parse(selectedWhen) <= Date.now() + 366 * 86400_000;

  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(draft)); } catch { /* optional storage */ } }, [draft, key]);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [draft.phase, complete]);
  function patch(value) { setDraft(old => ({ ...old, ...value })); }
  function phase(value) { setError(''); onStatus(''); patch({ phase: value }); }
  function no() { attempts.current = Math.min(attempts.current + 1, 1_000_000); patch({ attempts: attempts.current }); }
  function nextTime(event) {
    event.preventDefault();
    if (!validWhen) { setError('Kelajakdagi kun va vaqtni tanlang.'); return; }
    patch({ when: selectedWhen, phase: 'plan' }); setError('');
  }
  async function confirm(event) {
    event.preventDefault();
    if (busy.current || invite.preview) return;
    if (!validWhen || !draft.plan) { setError('Kun, vaqt va uchrashuv rejasini tanlang.'); return; }
    busy.current = true; setSaving(true); setError('');
    try {
      await api(`/invites/${invite.id}/accept`, { method: 'POST', json: {
        no_attempts: draft.attempts, meeting_response: { when: selectedWhen, plan: draft.plan, note: draft.note }
      } });
      // Re-read the server's frozen choices, including after an ambiguous network retry.
      const saved = await api(`/invites/${invite.id}`);
      if (!saved.details?.meeting_response) throw new Error('Javobni qayta ochib tekshiring.');
      setReceipt(saved.details.meeting_response); setComplete(true);
      tg?.HapticFeedback?.notificationOccurred('success');
    } catch (reason) { setError(reason?.message || 'Javob saqlanmadi. Qayta urinib ko‘ring.'); }
    finally { busy.current = false; setSaving(false); }
  }
  async function saveCalendar() {
    if (!receipt || exportBusy.current) return;
    exportBusy.current = true; setExporting(true); onStatus('');
    try {
      const file = await api(`/invites/${invite.id}/calendar`, { method: 'POST' });
      if (tg?.downloadFile && tg?.isVersionAtLeast?.('8.0') && !['weba', 'web', 'webk'].includes(tg.platform)) {
        tg.downloadFile(file, accepted => onStatus(accepted ? 'Kalendar faylini ochib, kalendarga qo‘shing.' : 'Saqlash bekor qilindi.'));
      } else {
        const link = document.createElement('a');
        link.href = file.url; link.download = file.file_name; link.referrerPolicy = 'no-referrer';
        document.body.append(link); link.click(); link.remove();
        onStatus('Kalendar faylini ochib, kalendarga qo‘shing.');
      }
    } catch (reason) {
      onStatus(reason instanceof TypeError ? 'Aloqa uzildi. Rejani saqlashga qayta urinib ko‘ring.'
        : reason?.message || 'Rejani saqlab bo‘lmadi. Qayta urinib ko‘ring.', true);
    }
    finally { exportBusy.current = false; setExporting(false); }
  }
  const title = text => <h1 ref={heading} tabIndex={-1}>{text}</h1>;
  return <section className={`invitation design-meeting meeting-flow meeting-${complete ? 'letter' : draft.phase}`}>
    {invite.preview && <p className="meeting-preview">Ko‘rinishni sinab ko‘rishingiz mumkin. Yakuniy javob yuborilmaydi.</p>}
    {error && <p className="meeting-error" role="alert">{error}</p>}
    {complete ? <>
      {title(receipt ? 'Biz uchun kichkina xat' : 'Taklif qabul qilingan')}
      {receipt ? <>
        <article className="meeting-letter-paper">
          <Icon className="meeting-letter-heart" />
          <h2>Aziz {recipient},</h2>
          <p>Endi hammasi aniq: uchrashuvimiz belgilandi. Bu rejani asrab qo‘yamiz. O‘sha kunni iliqlik bilan kutamiz.</p>
          <DateSummary when={receipt.when} />
          <p className="meeting-selected-plan"><Icon kind={plans.find(p => p.id === receipt.plan)?.icon} />{plans.find(p => p.id === receipt.plan)?.label}</p>
          {receipt.note && <p className="meeting-receiver-note">{receipt.note}</p>}
          <p>Bu uchrashuv biz uchun ajoyib xotiraga aylansin.</p>
          {sender && <p className="meeting-signature">— {sender} <Icon /></p>}
        </article>
        <button type="button" className="meeting-action" disabled={exporting} onClick={saveCalendar}><Icon kind="download" />{exporting ? 'Tayyorlanmoqda…' : 'Rejani saqlash'}</button>
        <p className="meeting-save-help">Kalendar faylini ochib, telefon kalendariga qo‘shing.</p>
      </> : <p>Bu avvalgi taklifda kun va reja qayd etilmagan.</p>}
    </> : draft.phase === 'intro' ? <>
      {title(recipient)}
      <div className="meeting-seal"><JoinedHeart progress={progress} /></div>
      <p className="description">Yurakning ikki bo‘lagini birlashtiring — kichkina savolim sizni kutyapti.</p>
      <div className="meeting-slider">
        <label htmlFor={`open-${invite.id}`}>Ochish uchun suring</label>
        <input id={`open-${invite.id}`} type="range" min="0" max="100" value={progress}
          aria-label="Yurakni birlashtirib taklifni ochish" onChange={event => {
            const value = Number(event.target.value); setProgress(value);
            if (value >= 95) phase('question');
          }} />
      </div>
      {sender && <p className="meeting-from">Kimdan: {sender}</p>}
    </> : draft.phase === 'question' ? <>
      <article className="meeting-question-paper">
        <p>Sizga munosabatim bor — balki umrning eng yaxshi xotiralaridan biri shunday boshlanar.</p>
        {renderMedia?.(invite)}
        {title(<>{recipient},<br />uchrashamizmi?</>)}
        <p className="description">{invite.description}</p>
        <Choice onYes={() => phase('celebrate')} onNo={no} attempts={draft.attempts} />
      </article>
    </> : draft.phase === 'celebrate' ? <>
      <div className="meeting-celebrate-heart"><Icon /></div>
      {title(<>Ajoyib,<br />uchrashamiz!</>)}
      <p>Endi kunni tanlab, bizning kichik rejamizni birga tuzamiz.</p>
      <button type="button" className="meeting-action" onClick={() => phase('when')}>Rejani tanlash <Icon kind="calendar" /></button>
    </> : draft.phase === 'when' ? <form onSubmit={nextTime}>
      <div className="meeting-form-top"><button type="button" onClick={() => phase('celebrate')}>Orqaga</button><span>1 / 2</span></div>
      {title('Kun va vaqtni tanlang')}
      <fieldset><legend>Qachon uchrashamiz?</legend>
        {slots.map(value => <label className={`meeting-time-option ${draft.choice === value ? 'selected' : ''}`} key={value}>
          <input type="radio" name="meeting-time" value={value} checked={draft.choice === value}
            onChange={() => patch({ choice: value, when: value })} />
          <span>{dateLabel(value)}<small><Icon kind="clock" />{timeLabel(value)}</small></span>
        </label>)}
        {slots.length > 0 && <p className="meeting-or">yoki</p>}
        {slots.length > 0 && <label className={`meeting-time-option ${customChoice ? 'selected' : ''}`}>
          <input type="radio" name="meeting-time" value="custom" checked={draft.choice === 'custom'} onChange={() => patch({ choice: 'custom' })} />
          <span><Icon kind="calendar" /> O‘zimga qulay vaqtni tanlayman</span>
        </label>}
        {customChoice && <MeetingDateTime date={draft.customDate} time={draft.customTime}
          onChange={value => patch({ ...value, choice: 'custom' })} />}
      </fieldset>
      <button className="meeting-action" type="submit" disabled={!validWhen}>Keyingi — rejani tanlash <Icon kind="arrow" /></button>
    </form> : <form onSubmit={confirm}>
      <div className="meeting-form-top"><button type="button" disabled={saving} onClick={() => phase('when')}>Vaqtga qaytish</button><span>2 / 2</span></div>
      {title('Reja va tilakni tanlang')}
      {validWhen && <DateSummary when={selectedWhen} />}
      <fieldset className="meeting-plan-options"><legend>Nima qilamiz?</legend>
        {plans.map(plan => <label key={plan.id} className={draft.plan === plan.id ? 'selected' : ''}>
          <input type="radio" name="meeting-plan" value={plan.id} checked={draft.plan === plan.id} disabled={saving} onChange={() => patch({ plan: plan.id })} />
          <Icon kind={plan.icon} /><span>{plan.label}</span>
        </label>)}
      </fieldset>
      <label className="meeting-note-label" htmlFor={`note-${invite.id}`}>Sizdan bir-ikki og‘iz — ixtiyoriy</label>
      <textarea id={`note-${invite.id}`} maxLength={300} rows={3} placeholder="Qisqa javob yozishingiz mumkin…" value={draft.note} disabled={saving} onChange={e => patch({ note: e.target.value })} />
      <p className="meeting-note-count">{draft.note.length}/300</p>
      <button className="meeting-action" type="submit" disabled={saving || invite.preview || !draft.plan || !validWhen}>{saving ? 'Saqlanmoqda…' : 'Uchrashuvni tasdiqlash'} <Icon kind="arrow" /></button>
      {invite.preview && <p className="meeting-preview">Bu ko‘rinish xolos. Taklifni botga qaytib tasdiqlang.</p>}
    </form>}
  </section>;
}
