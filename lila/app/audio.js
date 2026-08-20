// The casino soundboard. Everything synthesized with WebAudio oscillators:
// the repo carries no binary audio assets. Sound is enabled after the first
// user interaction (autoplay policy) with an obvious persisted mute.

let ctx = null;
let muted = localStorage.getItem('lila_muted') === '1';

export function isMuted() { return muted; }
export function setMuted(m) { muted = m; localStorage.setItem('lila_muted', m ? '1' : '0'); }

function ac() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

function tone(freq, dur, { type = 'sine', gain = 0.12, when = 0, glide = null } = {}) {
  if (muted) return;
  const c = ac();
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, c.currentTime + when);
  if (glide) o.frequency.exponentialRampToValueAtTime(glide, c.currentTime + when + dur);
  g.gain.setValueAtTime(gain, c.currentTime + when);
  g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + when + dur);
  o.connect(g).connect(c.destination);
  o.start(c.currentTime + when);
  o.stop(c.currentTime + when + dur + 0.02);
}

function noise(dur, { gain = 0.06, when = 0 } = {}) {
  if (muted) return;
  const c = ac();
  const len = c.sampleRate * dur;
  const buf = c.createBuffer(1, len, c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len);
  const src = c.createBufferSource();
  src.buffer = buf;
  const g = c.createGain();
  g.gain.value = gain;
  src.connect(g).connect(c.destination);
  src.start(c.currentTime + when);
}

export const sounds = {
  right() { tone(523, 0.09, { type: 'triangle' }); tone(784, 0.12, { type: 'triangle', when: 0.07 }); },
  left() { tone(140, 0.14, { type: 'square', gain: 0.09, glide: 90 }); },
  whooshRight() { noise(0.12, { gain: 0.05 }); tone(600, 0.1, { glide: 900, gain: 0.03 }); },
  whooshLeft() { noise(0.12, { gain: 0.05 }); tone(500, 0.1, { glide: 250, gain: 0.03 }); },
  snapBack() { tone(300, 0.06, { type: 'triangle', gain: 0.05 }); },
  deal() { noise(0.09, { gain: 0.045 }); tone(1200, 0.03, { gain: 0.02, when: 0.02 }); },
  chip() { tone(1800, 0.03, { type: 'square', gain: 0.05 }); tone(2400, 0.02, { type: 'square', gain: 0.03, when: 0.02 }); },
  jackpot() {
    tone(523, 0.12, { type: 'triangle' });
    tone(659, 0.12, { type: 'triangle', when: 0.11 });
    tone(1047, 0.3, { type: 'triangle', when: 0.22 });
    noise(0.25, { gain: 0.04, when: 0.2 });
  },
  ratchet() { for (let i = 0; i < 4; i++) tone(900 + i * 150, 0.025, { type: 'square', gain: 0.04, when: i * 0.045 }); },
  reelTick() { for (let i = 0; i < 6; i++) tone(1400, 0.02, { type: 'square', gain: 0.035, when: i * 0.05 }); tone(880, 0.12, { type: 'triangle', gain: 0.06, when: 0.32 }); },
  ember() { tone(80, 0.5, { type: 'sine', gain: 0.03 }); },
  streakHiss() { noise(0.3, { gain: 0.03 }); },
  flip() { noise(0.05, { gain: 0.04 }); tone(700, 0.04, { gain: 0.03 }); },
  payout(n = 8) { for (let i = 0; i < n; i++) tone(1500 + (i % 3) * 200, 0.03, { type: 'square', gain: 0.035, when: i * 0.06 }); },
};

export function pulse(el) {
  // iOS Safari has no web haptics: every sound pairs with a 120 ms visual pulse.
  el.classList.remove('pulse');
  void el.offsetWidth;
  el.classList.add('pulse');
  if (navigator.vibrate) navigator.vibrate(15);
}
