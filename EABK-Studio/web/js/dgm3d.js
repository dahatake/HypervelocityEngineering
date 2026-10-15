// FR-1040: 3D rendering of the diagrams. It draws exactly the graph that getState().diagram publishes
// (elements and relations), so 2D and 3D show the same managed data. Render-on-demand (no animation loop),
// which also respects "reduce motion".
import * as THREE from 'three';
import { t } from './i18n.js';
import { el, TYPE_COLOR } from './ui.js';

const COLOR = { ...TYPE_COLOR, system: '#39d0ff', state: '#b36bff', test: TYPE_COLOR.test };
const LAYER_ORDER = ['screen', 'api', 'data', 'other'];

function layout(g) {
  const n = g.elements.length;
  const idx = new Map(g.elements.map((e, i) => [e.id, i]));
  const R = Math.max(80, Math.sqrt(n) * 28);
  const P = g.elements.map((_, i) => {
    const y = n > 1 ? 1 - (i / (n - 1)) * 2 : 0, r = Math.sqrt(Math.max(0, 1 - y * y)), th = i * 2.399963;
    return { x: Math.cos(th) * r * R, y: y * R, z: Math.sin(th) * r * R, vx: 0, vy: 0, vz: 0 };
  });
  const edges = g.relations.map((r) => [idx.get(r.from), idx.get(r.to)]).filter(([a, b]) => a != null && b != null && a !== b);
  const groups = new Map();
  g.elements.forEach((e, i) => { if (e.group) { if (!groups.has(e.group)) groups.set(e.group, []); groups.get(e.group).push(i); } });
  const layered = g.kind === 'layers';
  const iters = n > 400 ? 50 : n > 150 ? 90 : 160;
  for (let it = 0; it < iters; it++) {
    const cool = 1 - it / iters;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = P[i], b = P[j];
      let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z; const d2 = dx * dx + dy * dy + dz * dz + 1, d = Math.sqrt(d2), f = 2600 / d2;
      dx /= d; dy /= d; dz /= d;
      a.vx += dx * f; a.vy += dy * f; a.vz += dz * f; b.vx -= dx * f; b.vy -= dy * f; b.vz -= dz * f;
    }
    for (const [i, j] of edges) {
      const a = P[i], b = P[j]; const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1, f = (d - 70) * 0.02;
      a.vx += (dx / d) * f; a.vy += (dy / d) * f; a.vz += (dz / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f; b.vz -= (dz / d) * f;
    }
    for (const ids of groups.values()) {
      let cx = 0, cy = 0, cz = 0; for (const i of ids) { cx += P[i].x; cy += P[i].y; cz += P[i].z; }
      cx /= ids.length; cy /= ids.length; cz /= ids.length;
      for (const i of ids) { P[i].vx += (cx - P[i].x) * 0.02; P[i].vy += (cy - P[i].y) * 0.02; P[i].vz += (cz - P[i].z) * 0.02; }
    }
    for (const p of P) { p.vx -= p.x * 0.004; p.vy -= p.y * 0.004; p.vz -= p.z * 0.004; p.x += Math.max(-12, Math.min(12, p.vx)) * cool; p.y += Math.max(-12, Math.min(12, p.vy)) * cool; p.z += Math.max(-12, Math.min(12, p.vz)) * cool; p.vx *= 0.55; p.vy *= 0.55; p.vz *= 0.55; }
  }
  if (layered) g.elements.forEach((e, i) => { P[i].y = (1.5 - Math.max(0, LAYER_ORDER.indexOf(e.group))) * 110; });
  return P;
}

export function mount3d(host, g, { onPick } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });   // throws without WebGL → caller falls back to 2D
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  renderer.setClearColor(0x000000, 0);
  const canvas = renderer.domElement;
  canvas.style.display = 'block'; canvas.style.width = '100%'; canvas.style.height = '100%';
  const stage = el('div', { class: 'dgm3d-stage', tabindex: '0', role: 'group', 'aria-roledescription': '3D', 'aria-label': t('dim.3dlabel', { n: g.elements.length, r: g.relations.length }), 'data-testid': 'dgm-3d-stage' }, canvas);
  const hint = el('div', { class: 'mini dgm3d-hint' }, t('dim.hint'));
  host.append(stage, hint);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 1, 10000);
  const P = layout(g);
  const idx = new Map(g.elements.map((e, i) => [e.id, i]));
  const world = new THREE.Group(); scene.add(world);

  const dot = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); const gr = x.createRadialGradient(32, 32, 0, 32, 32, 30); gr.addColorStop(0, '#fff'); gr.addColorStop(0.7, '#fff'); gr.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = gr; x.beginPath(); x.arc(32, 32, 30, 0, 7); x.fill(); return new THREE.CanvasTexture(c); })();
  const sprites = g.elements.map((e, i) => {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: dot, color: new THREE.Color(COLOR[e.type] || '#8aa1b5'), transparent: true, depthTest: false }));
    s.position.set(P[i].x, P[i].y, P[i].z); s.scale.set(16, 16, 1); s.renderOrder = 5; world.add(s); return s;
  });
  const arr = [];
  for (const r of g.relations) { const a = idx.get(r.from), b = idx.get(r.to); if (a == null || b == null) continue; arr.push(P[a].x, P[a].y, P[a].z, P[b].x, P[b].y, P[b].z); }
  const lineGeo = new THREE.BufferGeometry(); lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
  world.add(new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({ color: 0x7f9bff, transparent: true, opacity: 0.45 })));

  const deg = new Map(); for (const r of g.relations) { deg.set(r.from, (deg.get(r.from) || 0) + 1); deg.set(r.to, (deg.get(r.to) || 0) + 1); }
  const labelIds = new Set([...g.elements].sort((a, b) => (deg.get(b.id) || 0) - (deg.get(a.id) || 0)).slice(0, 120).map((e) => e.id));
  const texs = [];
  const labelOf = (e, i, color) => {
    const c = document.createElement('canvas'); c.width = 512; c.height = 64; const x = c.getContext('2d');
    x.font = '500 28px "Segoe UI","Yu Gothic UI",sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
    x.lineWidth = 6; x.strokeStyle = 'rgba(5,8,20,.9)'; const s = e.label.slice(0, 30); x.strokeText(s, 256, 34); x.fillStyle = color; x.fillText(s, 256, 34);
    const tex = new THREE.CanvasTexture(c); tex.minFilter = THREE.LinearFilter; texs.push(tex);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false })); sp.scale.set(104, 13, 1); sp.position.set(P[i].x, P[i].y + 14, P[i].z); sp.renderOrder = 10; world.add(sp); return sp;
  };
  g.elements.forEach((e, i) => { if (labelIds.has(e.id)) labelOf(e, i, '#e8eefc'); });
  let selLabel = null;

  let maxR = 1; for (const p of P) maxR = Math.max(maxR, Math.hypot(p.x, p.y, p.z));
  const cam = { th: 0.6, ph: 1.05, r: maxR * 2.1 + 70 };
  const target = new THREE.Vector3(0, 0, 0);
  let W = 1, H = 1, dead = false, raf = 0;
  const draw = () => {
    raf = 0; if (dead) return;
    camera.position.set(target.x + cam.r * Math.sin(cam.ph) * Math.sin(cam.th), target.y + cam.r * Math.cos(cam.ph), target.z + cam.r * Math.sin(cam.ph) * Math.cos(cam.th));
    camera.lookAt(target); camera.updateMatrixWorld(); renderer.render(scene, camera);
  };
  const redraw = () => { if (!raf && !dead) raf = requestAnimationFrame(draw); };
  const resize = () => { const r = stage.getBoundingClientRect(); W = Math.max(1, r.width); H = Math.max(1, r.height); renderer.setSize(W, H, false); camera.aspect = W / H; camera.updateProjectionMatrix(); redraw(); };
  const ro = new ResizeObserver(resize); ro.observe(stage); resize();

  // input: drag = rotate, wheel / +- = zoom, arrows = rotate (keyboard), click = select
  let drag = null, moved = false;
  stage.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY }; moved = false; stage.setPointerCapture?.(e.pointerId); });
  stage.addEventListener('pointermove', (e) => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true; drag = { x: e.clientX, y: e.clientY }; cam.th -= dx * 0.008; cam.ph = Math.max(0.15, Math.min(Math.PI - 0.15, cam.ph - dy * 0.008)); redraw(); });
  stage.addEventListener('pointerup', (e) => {
    drag = null;
    if (moved) return;
    const r = canvas.getBoundingClientRect(); let best = null, bd = 18;
    const v = new THREE.Vector3();
    sprites.forEach((s, i) => { v.copy(s.position).project(camera); if (v.z > 1) return; const d = Math.hypot((v.x * 0.5 + 0.5) * r.width - (e.clientX - r.left), (-v.y * 0.5 + 0.5) * r.height - (e.clientY - r.top)); if (d < bd) { bd = d; best = i; } });
    if (best != null) onPick?.(g.elements[best].id);
  });
  stage.addEventListener('wheel', (e) => { e.preventDefault(); cam.r = Math.max(40, Math.min(maxR * 8, cam.r * (e.deltaY > 0 ? 1.12 : 0.89))); redraw(); }, { passive: false });
  stage.addEventListener('keydown', (e) => {
    const k = e.key; let used = true;
    if (k === 'ArrowLeft') cam.th -= 0.12; else if (k === 'ArrowRight') cam.th += 0.12;
    else if (k === 'ArrowUp') cam.ph = Math.max(0.15, cam.ph - 0.1); else if (k === 'ArrowDown') cam.ph = Math.min(Math.PI - 0.15, cam.ph + 0.1);
    else if (k === '+' || k === '=') cam.r = Math.max(40, cam.r * 0.89); else if (k === '-') cam.r = Math.min(maxR * 8, cam.r * 1.12);
    else used = false;
    if (used) { e.preventDefault(); redraw(); }
  });

  return {
    setSelected(id) {
      sprites.forEach((s, i) => { const on = g.elements[i].id === id; s.scale.set(on ? 28 : 16, on ? 28 : 16, 1); s.material.color.set(on ? '#ffffff' : (COLOR[g.elements[i].type] || '#8aa1b5')); });
      if (selLabel) { world.remove(selLabel); selLabel.material.dispose(); selLabel = null; }
      const i = idx.get(id); if (i != null && !labelIds.has(id)) selLabel = labelOf(g.elements[i], i, '#ffffff');
      redraw();
    },
    destroy() {
      dead = true; cancelAnimationFrame(raf); ro.disconnect();
      scene.traverse((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
      texs.forEach((x) => x.dispose()); dot.dispose();
      renderer.dispose(); renderer.forceContextLoss?.();
    },
  };
}
