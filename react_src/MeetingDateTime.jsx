import React, { useId, useRef, useState } from 'react';

const months = ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun', 'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr'];
const week = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'];
const pad = value => String(value).padStart(2, '0');
const dayValue = date => date.toISOString().slice(0, 10);
const localDay = value => dayValue(new Date(value + 5 * 3600_000));
const parseDay = value => new Date(`${value}T12:00:00Z`);

export default function MeetingDateTime({ date, time, onChange }) {
  const now = Date.now();
  const limit = now + 366 * 86400_000;
  const today = localDay(now);
  const last = localDay(limit);
  const initial = date >= today && date <= last ? date : today;
  const [month, setMonth] = useState(initial.slice(0, 7));
  const labelId = useId();
  const days = useRef(null);
  const first = parseDay(`${month}-01`);
  const year = first.getUTCFullYear();
  const monthIndex = first.getUTCMonth();
  const count = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
  const offset = (first.getUTCDay() + 6) % 7;
  const hour = time.split(':')[0] || '';
  const minute = time.split(':')[1] || '';
  const available = (h, m) => {
    if (!date) return true;
    const stamp = Date.parse(`${date}T${pad(h)}:${pad(m)}+05:00`);
    return stamp > now && stamp <= limit;
  };
  const canSelectDay = value => value >= today && value <= last &&
    Date.parse(`${value}T23:59+05:00`) > now;
  function moveMonth(change) {
    const next = new Date(Date.UTC(year, monthIndex + change, 1, 12));
    setMonth(dayValue(next).slice(0, 7));
  }
  function choose(value) { onChange({ customDate: value }); }
  function navigate(event, value) {
    const shifts = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (!(event.key in shifts)) return;
    event.preventDefault();
    const next = parseDay(value);
    next.setUTCDate(next.getUTCDate() + shifts[event.key]);
    const target = dayValue(next);
    if (!canSelectDay(target)) return;
    setMonth(target.slice(0, 7));
    requestAnimationFrame(() => days.current?.querySelector(`[data-day="${target}"]`)?.focus());
  }
  const selectedStamp = date && time ? Date.parse(`${date}T${time}+05:00`) : NaN;
  const invalid = Number.isFinite(selectedStamp) && (selectedStamp <= now || selectedStamp > limit);
  const selectedLabel = date ? `${parseDay(date).getUTCDate()} ${months[parseDay(date).getUTCMonth()].toLowerCase()} ${parseDay(date).getUTCFullYear()}` : 'Kalendar ichidan kunni tanlang';

  return <div className="meeting-picker">
    <div className="meeting-calendar" role="group" aria-label="Uchrashuv kalendari">
      <div className="meeting-month-nav">
        <button type="button" aria-label="Oldingi oy" disabled={month <= today.slice(0, 7)} onClick={() => moveMonth(-1)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" aria-hidden="true"><path d="m14 6-6 6 6 6" /></svg>
        </button>
        <p id={labelId} aria-live="polite">{months[monthIndex]} {year}</p>
        <button type="button" aria-label="Keyingi oy" disabled={month >= last.slice(0, 7)} onClick={() => moveMonth(1)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" aria-hidden="true"><path d="m10 6 6 6-6 6" /></svg>
        </button>
      </div>
      <div className="meeting-week" aria-hidden="true">{week.map(day => <span key={day}>{day}</span>)}</div>
      <div className="meeting-days" ref={days} role="group" aria-labelledby={labelId}>
        {Array.from({ length: offset }, (_, i) => <span key={`empty-${i}`} />)}
        {Array.from({ length: count }, (_, i) => {
          const value = `${month}-${pad(i + 1)}`;
          return <button type="button" key={value} data-day={value}
            aria-label={`${i + 1} ${months[monthIndex].toLowerCase()} ${year}`}
            aria-pressed={date === value} aria-current={value === today ? 'date' : undefined}
            disabled={!canSelectDay(value)} onClick={() => choose(value)} onKeyDown={event => navigate(event, value)}>{i + 1}</button>;
        })}
      </div>
    </div>
    <p className="meeting-picked-day" role="status">{selectedLabel}</p>
    <div className="meeting-time-selects">
      <label>Soat<select aria-label="Soat" value={hour} onChange={event => onChange({ customTime: `${event.target.value}:${minute || '00'}` })} required>
        <option value="" disabled>Tanlang</option>
        {Array.from({ length: 24 }, (_, h) => <option key={h} value={pad(h)} disabled={!Array.from({ length: 60 }, (_, m) => available(h, m)).some(Boolean)}>{pad(h)}</option>)}
      </select></label>
      <span aria-hidden="true">:</span>
      <label>Daqiqa<select aria-label="Daqiqa" value={minute} onChange={event => onChange({ customTime: `${hour}:${event.target.value}` })} disabled={!hour} required>
        <option value="" disabled>Tanlang</option>
        {Array.from({ length: 60 }, (_, m) => <option key={m} value={pad(m)} disabled={hour !== '' && !available(Number(hour), m)}>{pad(m)}</option>)}
      </select></label>
    </div>
    <p className="meeting-picker-help">O‘zbekiston vaqti (UTC+5). Kelgusi bir yil ichidagi vaqtni tanlang.</p>
    {invalid && <p className="meeting-error" role="alert">Bu vaqtni tanlab bo‘lmaydi. Kelajakdagi kun va vaqtni tanlang.</p>}
  </div>;
}
