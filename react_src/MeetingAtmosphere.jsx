import React, { useEffect, useRef, useState } from 'react';
import musicUrl from './assets/meeting-love-you.mp3';

export default function MeetingAtmosphere({ reaction }) {
  const audio = useRef(null);
  const enabled = useRef(false);
  const start = useRef(() => {});
  const stop = useRef(() => {});
  const sound = useRef(null);
  const [on, setOn] = useState(false);
  const [playing, setPlaying] = useState(false);
  enabled.current = on;

  useEffect(() => {
    const player = audio.current;
    let disposed = false, pending = false, restart = false, fade;
    function pause() {
      restart = false; clearInterval(fade); player.pause();
      if (!disposed) setPlaying(false);
    }
    async function play() {
      if (disposed || !enabled.current || document.hidden || !player.paused) return;
      if (pending) { restart = true; return; }
      pending = true; restart = false;
      player.volume = 0;
      try {
        if (!player.hasAttribute('src')) player.src = musicUrl;
        await player.play();
        if (disposed || !enabled.current || document.hidden) { pause(); return; }
        setPlaying(true);
        clearInterval(fade);
        fade = setInterval(() => {
          player.volume = Math.min(0.23, player.volume + 0.012);
          if (player.volume >= 0.23) clearInterval(fade);
        }, 100);
      } catch { if (!disposed) setPlaying(false); }
      finally { pending = false; if (restart && !disposed) { restart = false; play(); } }
    }
    function gesture(event) {
      if (event.target.closest?.('[data-music-toggle]') || !enabled.current) return;
      play();
      const Context = window.AudioContext || window.webkitAudioContext;
      if (Context) {
        sound.current ||= new Context();
        sound.current.resume().catch(() => {});
      }
    }
    function visibility() { if (document.hidden) pause(); else play(); }
    start.current = play; stop.current = pause;
    document.addEventListener('pointerdown', gesture, true);
    document.addEventListener('keydown', gesture, true);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', pause);
    window.addEventListener('pageshow', visibility);
    const tg = window.Telegram?.WebApp;
    tg?.onEvent?.('deactivated', pause);
    tg?.onEvent?.('activated', play);
    return () => {
      disposed = true; pause();
      document.removeEventListener('pointerdown', gesture, true);
      document.removeEventListener('keydown', gesture, true);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', pause);
      window.removeEventListener('pageshow', visibility);
      tg?.offEvent?.('deactivated', pause); tg?.offEvent?.('activated', play);
      sound.current?.close().catch(() => {}); sound.current = null;
    };
  }, []);

  useEffect(() => {
    const context = sound.current;
    if (!reaction || !enabled.current || !context || context.state !== 'running') return;
    // A soft, short bubble pop; the music toggle controls both sounds.
    const oscillator = context.createOscillator(), gain = context.createGain();
    oscillator.type = 'sine'; oscillator.frequency.setValueAtTime(420,context.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(110,context.currentTime + 0.12);
    gain.gain.setValueAtTime(0.025,context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001,context.currentTime + 0.15);
    oscillator.connect(gain); gain.connect(context.destination);
    oscillator.start(); oscillator.stop(context.currentTime + 0.16);
    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
  }, [reaction]);

  function toggle() {
    const next = !on || !playing;
    enabled.current = next; setOn(next);
    if (next) start.current(); else stop.current();
  }
  return <div className="meeting-atmosphere">
    <audio ref={audio} loop preload="none" playsInline onPause={() => setPlaying(false)} onPlaying={() => setPlaying(true)} />
    <div className="meeting-sticker-stage" aria-hidden="true">
      {reaction && <div key={reaction.id} className={`meeting-sticker reaction-${reaction.kind}`}>
        <span className="sticker-balloon">{reaction.emoji}</span>
        {Array.from({length:8},(_,i) => <i key={i} style={{'--angle':`${i*45}deg`,'--particle':i%2 ? '#B83262' : '#B59BCC'}}>♥</i>)}
      </div>}
    </div>
    <button type="button" className="meeting-music" data-music-toggle aria-pressed={on && playing} onClick={toggle}>
      <span aria-hidden="true">{on && playing ? '♫' : '♪'}</span>
      {on && playing ? 'Ovozni o‘chirish' : 'Musiqani yoqish'}
    </button>
  </div>;
}
