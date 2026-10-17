// FR-1054: music and sound effects of the RPG-style map, synthesised at run time with the Web Audio API.
// No audio file, sound font or library is fetched or bundled; nothing here touches the network (AC-291).
// The tunes are original short phrases written for this screen (AC-293: see docs/rpg-originality.md).
// The AudioContext is created only after the user turns the sound on (AC-294), and sound is muted at first (PARAM-041).
const SEMI = (n) => 261.63 * Math.pow(2, n / 12);

// scene -> { lead: semitones from C4 (null = rest), bass root, step seconds, wave }
export const SCENES = {
  field: { lead: [0, 2, 4, 7, 4, 2, 0, 4, 7, 9, 7, 4, 2, 5, 9, 7, 5, 2, 0, -3, 0, 2, 4, 2, 0, null, -1, null], bass: [-12, -5, -12, -7], step: 0.26, wave: 'triangle' },
  town: { lead: [4, 7, 9, 7, 4, 2, 0, 2, 4, null, 2, 4, 5, 4, 2, 0, -1, 2, 4, null, 7, 5, 4, 2], bass: [-8, -1, -5, -1], step: 0.3, wave: 'sine' },
  castle: { lead: [0, 0, 3, 7, 5, 3, 2, -2, 0, 0, 3, 7, 8, 7, 5, 3, 2, null, -2, null, 0, null, null, null], bass: [-12, -12, -9, -7], step: 0.34, wave: 'square' },
};

// name -> [[semitone, start, length, wave, gain], ...]
export const SOUND_EFFECTS = {
  move: [[-5, 0, 0.05, 'square', 0.05]],
  confirm: [[7, 0, 0.07, 'square', 0.07], [12, 0.07, 0.1, 'square', 0.07]],
  cancel: [[7, 0, 0.07, 'square', 0.07], [0, 0.07, 0.1, 'square', 0.07]],
  text: [[19, 0, 0.025, 'square', 0.03]],
  menu: [[9, 0, 0.05, 'triangle', 0.08]],
  blocked: [[-17, 0, 0.08, 'sawtooth', 0.05]],
};

export function createAudio({ initialMuted = true } = {}) {
  let ctx = null, master = null, timer = 0, muted = !!initialMuted;
  let scene = 'field', stepIdx = 0, nextAt = 0;
  const stats = { played: {}, requested: {}, scenes: [] };

  function ensure() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.5;
    master.connect(ctx.destination);
    return ctx;
  }
  function tone(freq, at, len, wave, gain) {
    if (!ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = wave; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, at);
    g.gain.linearRampToValueAtTime(gain, at + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, at + len);
    o.connect(g); g.connect(master);
    o.start(at); o.stop(at + len + 0.02);
  }
  function schedule() {
    if (!ctx || muted) return;
    const sc = SCENES[scene];
    while (nextAt < ctx.currentTime + 0.4) {
      const at = Math.max(nextAt, ctx.currentTime + 0.02);
      const n = sc.lead[stepIdx % sc.lead.length];
      if (n != null) tone(SEMI(n), at, sc.step * 0.9, sc.wave, 0.06);
      if (stepIdx % 4 === 0) tone(SEMI(sc.bass[(stepIdx / 4) % sc.bass.length | 0]), at, sc.step * 3.4, 'triangle', 0.05);
      stepIdx++; nextAt = at + sc.step;
    }
  }
  function startMusic() {
    if (timer || !ctx) return;
    nextAt = ctx.currentTime + 0.05;
    timer = setInterval(schedule, 120);
    schedule();
  }
  function stopMusic() { if (timer) { clearInterval(timer); timer = 0; } }

  return {
    get muted() { return muted; },
    get scene() { return scene; },
    get started() { return !!ctx; },
    stats,
    // Called only from a user's key / click, never on load (AC-294).
    setMuted(m) {
      muted = !!m;
      if (muted) { stopMusic(); ctx?.suspend?.(); return; }
      if (!ensure()) return;
      ctx.resume?.();
      startMusic();
    },
    setScene(name) {
      if (!SCENES[name] || name === scene) return;
      scene = name; stepIdx = 0; stats.scenes.push(name);
      if (ctx) nextAt = ctx.currentTime + 0.05;
    },
    play(name) {
      stats.requested[name] = (stats.requested[name] || 0) + 1;
      if (muted || !ctx) return;
      const def = SOUND_EFFECTS[name];
      if (!def) return;
      stats.played[name] = (stats.played[name] || 0) + 1;
      const t0 = ctx.currentTime;
      for (const [n, at, len, wave, gain] of def) tone(SEMI(n), t0 + at, len, wave, gain);
    },
    destroy() { stopMusic(); try { ctx?.close?.(); } catch { /* already closed */ } ctx = null; },
  };
}
