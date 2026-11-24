import React, { useLayoutEffect, useRef } from 'react';

const pad = n => String(n).padStart(2, '0');
const rowHeight = 44;

export function minuteBounds(date) {
  const start = Date.parse(date + 'T00:00+05:00');
  const now = Date.now();
  return [Math.max(0, Math.floor((now - start) / 60000) + 1),
    Math.min(1439, Math.floor((now + 366 * 86400000 - start) / 60000))];
}

export function clockValue(minutes) {
  return pad(Math.floor(minutes / 60)) + ':' + pad(minutes % 60);
}

function Wheel({ label, value, min, max, onChange }) {
  const list = useRef(null);
  useLayoutEffect(() => {
    const index = value - min;
    if (Math.round(list.current.scrollTop / rowHeight) !== index)
      list.current.scrollTop = index * rowHeight;
  }, [value, min]);

  function key(event) {
    const values = { ArrowDown: value + 1, ArrowUp: value - 1, Home: min, End: max };
    if (!(event.key in values)) return;
    event.preventDefault();
    onChange(Math.min(max, Math.max(min, values[event.key])));
  }

  return <div><strong>{label}</strong>
    <div className="alarm-wheel" ref={list} role="spinbutton" tabIndex={0}
      aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value}
      onKeyDown={key} onScroll={event => {
        const next = Math.min(max, Math.max(min, min + Math.round(event.currentTarget.scrollTop / rowHeight)));
        if (next !== value) onChange(next);
      }}>
      {Array.from({ length: max-min+1 }, (_, i) => i+min).map(n =>
        <div aria-hidden="true" key={n} data-selected={n===value} onClick={() => onChange(n)}>{pad(n)}</div>)}
    </div>
  </div>;
}

export default function AlarmTime({date, time, onChange}) {
  const [low, high] = minuteBounds(date);
  if (!(low <= high)) return <p>Boshqa sanani tanlang.</p>;
  const [h,m] = time.split(':').map(Number);
  const total = Math.min(high, Math.max(low, h*60+m || 0));
  const hour = Math.floor(total/60);
  const change = n => onChange(clockValue(Math.min(high, Math.max(low, n))));
  return <div className="alarm-dial">
    <Wheel label="Soat" min={Math.floor(low/60)} max={Math.floor(high/60)} value={hour} onChange={n => change(n*60+total%60)} />
    <b aria-hidden="true">:</b>
    <Wheel label="Daqiqa" min={Math.max(0,low-hour*60)} max={Math.min(59,high-hour*60)} value={total%60} onChange={n => change(hour*60+n)} />
  </div>;
}
