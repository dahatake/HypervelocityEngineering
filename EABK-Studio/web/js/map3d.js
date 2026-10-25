// 3D traceability map (three.js): layers of goals / requirements / parts-and-data / source / tests with a cinematic camera.
import * as THREE from 'three';
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { create3d } from './sz3d.js';
import { mountShell, isArch, wantsEntityView, hasEntityStructure, setTab } from './semzoom.js';
import { mountMapTiers, tierState, tierPathOf, tierRank, tierKey, tierOfKey, tierShortLabel } from './maptiers.js';
import { shapeOf, isKnownKind, buildNodeObjects, buildLegend, buildStyleToggle, addSceneLights, loadStyle, saveStyle, normStyle, FX_BY_STYLE, kindName, shapeName } from './shapes3d.js';
import { createCameraRig } from './camera3d.js';
import { publishDim } from './dim.js';
import { el, colorOf, TYPE_COLOR, STATUS_COLOR, IMPL_COLOR, token, icon, showTip, hideTip, nodeTip } from './ui.js';

const LEVEL = { goal: 0, req: 1, ac: 2, entity: 3, part: 3, api: 3, table: 3, param: 3, question: 3, file: 4, case: 5 };
const LAYER_TYPES = ['goal', 'req', 'ac', 'entity', 'part', 'api', 'table', 'param', 'question', 'file', 'case'];
const prefs = { layers: new Set(['goal', 'req', 'entity', 'part', 'api', 'table', 'file', 'case']), color: 'type', kindFocus: null, style: loadStyle(), auto: !matchMedia('(prefers-reduced-motion: reduce)').matches };
const GAP = 95, SP = 6.5;

function mountGraph(host) {
  const toolbar = el('div', { class: 'toolbar' });
  const statusBox = el('div', { class: 'status' });
  const hint = el('div', { class: 'hint' });
  const mount3 = el('div', { class: 'fill map3d' });
  host.append(mount3, toolbar, statusBox, hint);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
  renderer.setClearColor(0x000000, 0);
  mount3.append(renderer.domElement);
  renderer.domElement.style.display = 'block';
  const scene = new THREE.Scene();
  addSceneLights(scene);
  const camera = new THREE.PerspectiveCamera(50, 1, 1, 8000);
  const world = new THREE.Group();
  scene.add(world);

  let W = 1, H = 1, dead = false, raf = 0;
  let nodes = [], idx = new Map(), P = null, pointsObj = null, baseLines = null, hiLines = null, parts = null;
  let labelPool = [], labelCache = new Map(), staticLabels = [], pinfo = [], labelHits = [];
  const cam = { target: new THREE.Vector3(), theta: 0.7, phi: 1.0, radius: 600, vt: 0, vp: 0 };
  let anim = null, tour = null, lastInput = performance.now(), drag = null, moved = false;
  // FR-1070 / FR-1071: カメラのプリセット。増分で cam を動かすので、選択・ズーム・絞り込み・手動の位置は失われない。
  const clampN = (n, a, b) => Math.min(b, Math.max(a, n));
  const rig = createCameraRig({ interact: mount3, applyDelta: (dl) => {
    cam.theta += dl.yaw; cam.phi = clampN(cam.phi + dl.pitch, 0.03, 3.05); cam.radius = clampN(cam.radius * Math.exp(dl.zoom), 20, 4000);
  } });
  host.append(rig.el);
  renderer.domElement.tabIndex = 0; renderer.domElement.setAttribute('aria-label', t('dim.hint'));

  let starsObj = null, shapeObjs = null, arrows = null, legendEl = null, styleEl = null, shapeItems = [], shapeDirty = true;
  const dotTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 32; const g = c.getContext('2d'); const gr = g.createRadialGradient(16, 16, 0, 16, 16, 16); gr.addColorStop(0, '#fff'); gr.addColorStop(0.5, '#fff'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 32, 32); return new THREE.CanvasTexture(c); })();
  // ---------- stars
  {
    const n = 1600, pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 2500 + Math.random() * 2500, a = Math.random() * 6.283, b = Math.acos(2 * Math.random() - 1);
      pos.set([r * Math.sin(b) * Math.cos(a), r * Math.cos(b), r * Math.sin(b) * Math.sin(a)], i * 3);
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    starsObj = new THREE.Points(g, new THREE.PointsMaterial({ color: 0x9fb4ff, size: 5, map: dotTex, alphaTest: 0.05, sizeAttenuation: false, transparent: true, opacity: 0.55, depthWrite: false }));
    scene.add(starsObj);
  }

  const nodeMat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { uScale: { value: 500 } },
    vertexShader: `attribute float size; attribute float alpha; varying vec3 vC; varying float vA;
      uniform float uScale; void main(){ vC=color; vA=alpha; vec4 mv=modelViewMatrix*vec4(position,1.); gl_PointSize=size*uScale/-mv.z; gl_Position=projectionMatrix*mv; }`,
    fragmentShader: `varying vec3 vC; varying float vA; void main(){ vec2 p=gl_PointCoord-.5; float d=length(p); if(d>.5) discard;
      float l=1.-length(p+vec2(.12,.14))*1.5; vec3 c=vC*(.5+.75*clamp(l,0.,1.)); float rim=smoothstep(.36,.5,d);
      gl_FragColor=vec4(mix(c,vC*1.3,rim*.5), vA*(1.-rim*.35)); }`,
    vertexColors: true,
  });

  // ---------- layout
  function visible() {
    return [...store.nodes.values()].filter((n) => prefs.layers.has(n.type) && (n.deg > 0 || ['goal', 'req', 'file', 'case'].includes(n.type)));
  }
  function layout3d(list) {
    const levels = [...new Set(list.map((n) => LEVEL[n.type]))].sort((a, b) => a - b);
    const yOf = new Map(levels.map((l, i) => [l, -i * GAP]));
    const out = new Map(), layers = [];
    const angleOf = (id) => { const p = out.get(id); return p ? Math.atan2(p.z, p.x) : null; };
    const order = [...levels].sort((a, b) => (a === 1 ? -1 : b === 1 ? 1 : a - b));
    for (const lv of order) {
      // FR-1063 AC-346: 2D と同じ上位層（種類→区分→領域）ごとのまとまり。階層に項目がない点だけ従来のまとまりを使う。
      const L = list.filter((n) => LEVEL[n.type] === lv).sort((a, b) => tierRank(tierPathOf(a)) - tierRank(tierPathOf(b)));
      const gmap = new Map();
      const gkey0 = (n) => (n.type === 'req' ? n.group : n.type === 'file' ? n.comp : n.type === 'ac' ? (store.node(n.req)?.group || 'ac') : n.type);
      const gkey = (n) => { const p = tierPathOf(n); return p ? tierKey(p) : gkey0(n); };
      for (const n of L) { const k = gkey(n); if (!gmap.has(k)) gmap.set(k, []); gmap.get(k).push(n); }
      const cl = [...gmap.entries()].map(([key, ns], i) => {
        let sx = 0, sy = 0, c = 0;
        for (const n of ns) for (const a of store.adj.get(n.id) || []) { const an = angleOf(a.id); if (an != null) { sx += Math.cos(an); sy += Math.sin(an); c++; } }
        const angle = c ? Math.atan2(sy, sx) : (i / gmap.size) * 6.283;
        const tier = tierOfKey(key), coll = !!tier && !tierState.mapOpen(tier);   // 畳んだ領域は件数つきの 1 つの塊にする
        return { key, ns, angle, tier, coll, r: coll ? 9 : SP * Math.sqrt(ns.length) * 0.62 + 6, x: 0, z: 0 };
      });
      if (lv === 1) cl.forEach((c, i) => (c.angle = (i / cl.length) * 6.283));
      let R = Math.max(28, cl.reduce((s, c) => s + 2 * c.r + 8, 0) / 6.283);
      if (lv === 0) R = Math.max(16, cl.reduce((s, c) => s + 2 * c.r, 0) / 6.283 * 0.6);
      cl.forEach((c) => { c.tx = Math.cos(c.angle) * R; c.tz = Math.sin(c.angle) * R; c.x = c.tx; c.z = c.tz; });
      for (let it = 0; it < 140; it++) {
        for (let i = 0; i < cl.length; i++) for (let j = i + 1; j < cl.length; j++) {
          const a = cl[i], b = cl[j]; let dx = b.x - a.x, dz = b.z - a.z; const d = Math.hypot(dx, dz) || 0.01, min = a.r + b.r + 6;
          if (d < min) { const f = (min - d) / 2 / d; a.x -= dx * f; a.z -= dz * f; b.x += dx * f; b.z += dz * f; }
        }
        for (const c of cl) { c.x += (c.tx - c.x) * 0.03; c.z += (c.tz - c.z) * 0.03; }
      }
      let maxR = 0;
      for (const c of cl) {
        c.ns.forEach((n, i) => {
          if (c.coll) { out.set(n.id, { x: c.x, z: c.z, y: yOf.get(lv), cg: c, first: i === 0 }); return; }
          const rr = SP * 0.62 * Math.sqrt(i + 0.5), a = i * 2.39996;
          out.set(n.id, { x: c.x + rr * Math.cos(a), z: c.z + rr * Math.sin(a), y: yOf.get(lv) + ((i % 3) - 1) * 1.6 });
        });
        maxR = Math.max(maxR, Math.hypot(c.x, c.z) + c.r);
      }
      layers.push({ lv, y: yOf.get(lv), R: maxR + 14, clusters: cl, types: [...new Set(L.map((n) => n.type))] });
    }
    return { out, layers };
  }

  function nodeColor(n) {
    if (n.type === 'req') {
      if (prefs.color === 'status') return STATUS_COLOR[n.statusKind] || STATUS_COLOR.unknown;
      if (prefs.color === 'impl') return IMPL_COLOR[n.impl];
    }
    return colorOf(n);
  }

  function labelSprite(text, color = token('--viz-cluster-name'), big = false) {
    const key = text + color + big;
    let tex = labelCache.get(key);
    if (!tex) {
      const c = document.createElement('canvas'); c.width = 512; c.height = 64;
      const g = c.getContext('2d');
      g.font = `${big ? 600 : 500} ${big ? 34 : 28}px "Segoe UI","Yu Gothic UI",sans-serif`;
      g.textBaseline = 'middle'; g.textAlign = 'center';
      g.lineWidth = 6; g.strokeStyle = token('--scene-stage-bg'); g.strokeText(text.slice(0, 34), 256, 34);
      g.fillStyle = color; g.fillText(text.slice(0, 34), 256, 34);
      tex = new THREE.CanvasTexture(c); tex.minFilter = THREE.LinearFilter;
      labelCache.set(key, tex);
    }
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false }));
    s.renderOrder = 10;
    return s;
  }

  function build() {
    for (const o of [...world.children]) { world.remove(o); o.traverse?.((x) => { x.geometry?.dispose?.(); }); }
    labelPool = []; staticLabels = []; labelCache.forEach((tx) => tx.dispose()); labelCache.clear();
    nodes = visible();
    idx = new Map(nodes.map((n, i) => [n.id, i]));
    const { out, layers } = layout3d(nodes);
    P = new Float32Array(nodes.length * 3);
    pinfo = []; labelHits = [];
    const colors = new Float32Array(nodes.length * 3), sizes = new Float32Array(nodes.length), alphas = new Float32Array(nodes.length).fill(1);
    const cc = new THREE.Color();
    nodes.forEach((n, i) => {
      const p = out.get(n.id);
      P.set([p.x, p.y, p.z], i * 3);
      cc.set(nodeColor(n)); colors.set([cc.r, cc.g, cc.b], i * 3);
      sizes[i] = p.cg ? (p.first ? 9.5 : 0.01) : n.type === 'goal' ? 11 : n.type === 'req' ? 5.2 : n.type === 'file' ? 4.4 : 4.8;
      pinfo[i] = p;
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(P, 3));
    g.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    g.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    g.setAttribute('alpha', new THREE.BufferAttribute(alphas, 1));
    pointsObj = new THREE.Points(g, nodeMat);
    pointsObj.frustumCulled = false;
    pointsObj.userData.base = sizes.slice();
    pointsObj.renderOrder = 5;
    pointsObj.visible = false;   // FR-1068: 点（球）ではなく、種別ごとのかたちのオブジェクトで描く。点は座標・大きさの保持にだけ使う
    world.add(pointsObj);
    buildNodeShapes(sizes);

    // base edges
    const ev = [], ec = [];
    for (const e of store.edges) {
      if (e.rel === 'member' || e.rel === 'ref') continue;
      const a = idx.get(e.s), b = idx.get(e.t);
      if (a == null || b == null) continue;
      cc.set(nodeColor(nodes[a]));
      ev.push(P[a * 3], P[a * 3 + 1], P[a * 3 + 2], P[b * 3], P[b * 3 + 1], P[b * 3 + 2]);
      ec.push(cc.r, cc.g, cc.b, cc.r * 0.6, cc.g * 0.6, cc.b * 0.6);
    }
    const lg = new THREE.BufferGeometry();
    lg.setAttribute('position', new THREE.Float32BufferAttribute(ev, 3)); lg.setAttribute('color', new THREE.Float32BufferAttribute(ec, 3));
    baseLines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.1, depthWrite: false }));
    baseLines.frustumCulled = false;
    world.add(baseLines);
    buildArrows(ev);

    // layers (discs + labels)
    for (const L of layers) {
      const disc = new THREE.Mesh(new THREE.CircleGeometry(L.R, 72), new THREE.MeshBasicMaterial({ color: 0x5f7bff, transparent: true, opacity: 0.045, side: THREE.DoubleSide, depthWrite: false }));
      disc.rotation.x = -Math.PI / 2; disc.position.y = L.y - 3;
      const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(Array.from({ length: 73 }, (_, i) => new THREE.Vector3(Math.cos(i / 72 * 6.2832) * L.R, L.y - 3, Math.sin(i / 72 * 6.2832) * L.R))), new THREE.LineBasicMaterial({ color: 0x7f9bff, transparent: true, opacity: 0.28 }));
      world.add(disc, ring);
      const name = L.types.map((ty) => t('type.' + ty)).join(' / ');
      const s = labelSprite(name, token('--viz-cluster-name'), true); s.scale.set(70, 8.75, 1); s.position.set(-L.R - 6, L.y, 0);
      world.add(s); staticLabels.push(s);
      for (const c of L.clusters) {
        if (!c.tier && c.ns.length < 2 && L.clusters.length > 12) continue;
        const text = c.tier ? `${c.coll ? '▸' : '▾'} ${tierShortLabel(c.tier).slice(0, 22)} (${c.ns.length})` : c.key.replace(/\.md$/, '');
        const lab = labelSprite(text, token('--viz-cluster-name')); lab.scale.set(38, 4.75, 1); lab.position.set(c.x, L.y + 7, c.z + c.r * 0.9 + 3);
        world.add(lab); staticLabels.push(lab);
        if (c.tier) labelHits.push({ tier: c.tier, count: c.ns.length, coll: c.coll, pos: lab.position.clone() });
      }
    }
    mount3.dataset.tiers = JSON.stringify(layers.flatMap((L) => L.clusters.filter((c) => c.tier).map((c) => ({ path: c.tier, count: c.ns.length, collapsed: c.coll, level: L.lv }))));
    // travelling particles + highlight edges
    hiLines = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }));
    hiLines.frustumCulled = false;
    world.add(hiLines);
    parts = null;
    const pg = new THREE.BufferGeometry(); pg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(300 * 3), 3));
    parts = new THREE.Points(pg, new THREE.PointsMaterial({ color: 0xffffff, size: 3.2, map: dotTex, alphaTest: 0.05, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }));
    parts.frustumCulled = false; parts.userData.edges = [];
    world.add(parts);
    applyStyle();
    renderLegend();
    applyHighlight();
  }

  // ---------- FR-1068: 種別ごとのかたち・凡例 / FR-1069: 演出スタイル（シーン構築の部品。カメラ周りとは独立）
  function buildNodeShapes(sizes) {
    shapeObjs?.group.removeFromParent(); shapeObjs?.dispose();
    const cc = new THREE.Color();
    shapeItems = nodes.map((n, i) => ({ id: n.id, kind: n.type, x: P[i * 3], y: P[i * 3 + 1], z: P[i * 3 + 2], size: Math.max(0.6, sizes[i] * 0.5), hidden: !!(pinfo[i]?.cg && !pinfo[i].first), color: new THREE.Color(nodeColor(n)) }));
    shapeObjs = buildNodeObjects(shapeItems);
    world.add(shapeObjs.group);
    shapeDirty = true;
  }
  // 関係の方向（矢じり）: 辺の終点の手前に円錐を置く。Software Engineering で表示する（FR-1069 AC-379）。
  function buildArrows(ev) {
    arrows?.removeFromParent(); arrows?.geometry?.dispose?.(); arrows?.material?.dispose?.();
    const n = Math.min(ev.length / 6, 4000);
    arrows = new THREE.InstancedMesh(new THREE.ConeGeometry(1.1, 3.2, 8), new THREE.MeshBasicMaterial({ color: 0x9fb4ff, transparent: true, opacity: 0.55 }), n);
    const a = new THREE.Vector3(), b = new THREE.Vector3(), dir = new THREE.Vector3(), m = new THREE.Matrix4(), q = new THREE.Quaternion(), one = new THREE.Vector3(1, 1, 1), up = new THREE.Vector3(0, 1, 0);
    for (let k = 0; k < n; k++) {
      a.set(ev[k * 6], ev[k * 6 + 1], ev[k * 6 + 2]); b.set(ev[k * 6 + 3], ev[k * 6 + 4], ev[k * 6 + 5]);
      dir.subVectors(b, a); const len = dir.length() || 1; dir.divideScalar(len);
      q.setFromUnitVectors(up, dir);
      m.compose(b.clone().addScaledVector(dir, -Math.min(5, len * 0.4)), q, one);
      arrows.setMatrixAt(k, m);
    }
    arrows.frustumCulled = false; arrows.userData.kind = 'arrows';
    world.add(arrows);
  }
  const fxSet = () => new Set(FX_BY_STYLE[prefs.style] || []);
  function applyStyle() {
    mount3.dataset.style = prefs.style;
    mount3.dataset.fx = (FX_BY_STYLE[prefs.style] || []).join(',') || 'none';
    const ent = prefs.style === 'entertainment';
    if (starsObj) starsObj.visible = ent;
    if (parts) parts.visible = ent;
    if (arrows) arrows.visible = !ent;
    shapeDirty = true;
  }
  function setStyle(v) {
    prefs.style = normStyle(v); saveStyle(prefs.style);   // 保存はスタイル名だけ。再構築しないので、選択・ズーム・絞り込み・カメラは保たれる
    applyStyle(); renderStyleToggle();
  }
  function renderStyleToggle() {
    const next = buildStyleToggle(prefs.style, setStyle);
    if (styleEl) styleEl.replaceWith(next); else host.append(next);
    styleEl = next;
  }
  // 凡例の種別は、いま描かれているノード（nodes()）の種別そのもの。未知の種別は「その他」になる。
  function displayedNodes() { return shapeItems.filter((s) => !s.hidden).map((s) => ({ id: s.id, kind: s.kind, shape: shapeOf(s.kind) })); }
  function renderLegend() {
    const cnt = new Map();
    for (const s of shapeItems) { if (s.hidden) continue; const e = cnt.get(s.kind) || { kind: s.kind, color: '#' + s.color.getHexString(), count: 0 }; e.count++; cnt.set(s.kind, e); }
    const next = buildLegend([...cnt.values()], { focus: prefs.kindFocus, onFocus: (k) => { const had = k || prefs.kindFocus; prefs.kindFocus = k; shapeDirty = true; renderLegend(); legendEl.querySelector(`[data-kind="${CSS.escape(had)}"]`)?.focus(); } });
    if (legendEl) legendEl.replaceWith(next); else host.append(next);
    legendEl = next;
  }
  function refreshShapes(now) {
    const fx = fxSet();
    if (!shapeObjs || !(shapeDirty || fx.size)) return;
    shapeDirty = false;
    shapeObjs.apply({ now, fx, focusKind: prefs.kindFocus, selected: store.selected && idx.has(store.selected) ? idx.get(store.selected) : -1,
      dim: (i) => !!curSet && !curSet.has(nodes[i].id), grow: (i) => (curSet && curSet.has(nodes[i].id) ? 1.3 : 1) });
  }

  // ---------- highlight
  let curSet = null;
  function applyHighlight() {
    if (!pointsObj) return;
    const hov = store.hover && idx.has(store.hover) ? store.related(store.hover, 1) : null;
    const set = hov || store.activeSet();
    curSet = set; shapeDirty = true;
    const al = pointsObj.geometry.attributes.alpha, sz = pointsObj.geometry.attributes.size, base = pointsObj.userData.base;
    nodes.forEach((n, i) => {
      const on = !set || set.has(n.id);
      al.array[i] = on ? 1 : 0.09;
      sz.array[i] = base[i] * (set && on ? 1.3 : 1);
    });
    al.needsUpdate = true; sz.needsUpdate = true;
    baseLines.material.opacity = set ? 0.025 : 0.1;
    // highlight edges
    const v = [], c = [], ed = [], cc = new THREE.Color();
    if (set) {
      for (const e of store.edges) {
        if (e.rel === 'member' || !set.has(e.s) || !set.has(e.t)) continue;
        const a = idx.get(e.s), b = idx.get(e.t);
        if (a == null || b == null) continue;
        cc.set(nodeColor(nodes[a]));
        v.push(P[a * 3], P[a * 3 + 1], P[a * 3 + 2], P[b * 3], P[b * 3 + 1], P[b * 3 + 2]);
        c.push(cc.r, cc.g, cc.b, 1, 1, 1);
        ed.push([a, b, Math.random()]);
      }
    }
    hiLines.geometry.dispose();
    hiLines.geometry = new THREE.BufferGeometry();
    hiLines.geometry.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
    hiLines.geometry.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
    parts.userData.edges = ed.slice(0, 300);
    parts.geometry.setDrawRange(0, parts.userData.edges.length);
    // labels for the active nodes
    for (const s of labelPool) world.remove(s);
    labelPool = [];
    if (set && set.size <= 60) {
      for (const id of set) {
        const i = idx.get(id); if (i == null) continue;
        const n = nodes[i];
        const s = labelSprite(n.label + (n.type === 'req' || n.type === 'goal' ? ' ' + (n.title || '').slice(0, 12) : ''), id === store.selected ? token('--viz-sel') : token('--viz-cluster-name'));
        s.scale.set(34, 4.25, 1); s.position.set(P[i * 3], P[i * 3 + 1] + 5.5, P[i * 3 + 2]);
        world.add(s); labelPool.push(s);
      }
    }
    renderStatus();
  }

  // ---------- camera
  const sph = new THREE.Vector3();
  function placeCamera() {
    const { theta, phi, radius, target } = cam;
    sph.set(Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta)).multiplyScalar(radius);
    camera.position.copy(target).add(sph);
    camera.lookAt(target);
  }
  const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  function fly(to, ms = 1400) {
    const from = { target: cam.target.clone(), theta: cam.theta, phi: cam.phi, radius: cam.radius };
    let dt = to.theta ?? cam.theta; // shortest way round
    dt = from.theta + Math.atan2(Math.sin(dt - from.theta), Math.cos(dt - from.theta));
    anim = { from, to: { target: to.target ?? from.target, theta: dt, phi: to.phi ?? cam.phi, radius: to.radius ?? cam.radius }, t0: performance.now(), ms };
  }
  function stepAnim(now) {
    if (!anim) return;
    const p = Math.min(1, (now - anim.t0) / anim.ms), e = ease(p);
    const { from, to } = anim;
    cam.target.lerpVectors(from.target, to.target, e);
    cam.theta = from.theta + (to.theta - from.theta) * e;
    cam.phi = from.phi + (to.phi - from.phi) * e;
    const lift = 1 + 0.35 * Math.sin(Math.PI * p) * Math.min(1, from.target.distanceTo(to.target) / 120);
    cam.radius = (from.radius + (to.radius - from.radius) * e) * lift;
    if (p >= 1) anim = null;
  }
  function boundsOf(ids) {
    const box = new THREE.Box3(); let c = 0;
    for (const id of ids) { const i = idx.get(id); if (i == null) continue; box.expandByPoint(new THREE.Vector3(P[i * 3], P[i * 3 + 1], P[i * 3 + 2])); c++; }
    return c ? box : null;
  }
  function viewFor(ids, extra = 1.0) {
    const box = boundsOf(ids); if (!box) return null;
    const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    const rad = Math.max(size.length() / 2, 14);
    const fov = (camera.fov * Math.PI) / 180;
    return { target: center, radius: Math.max(50, (rad / Math.sin(fov / 2)) * 0.62 * extra) };
  }
  const allIds = () => nodes.map((n) => n.id);
  function bird(kind = 'bird', keepTour = false) {
    if (!keepTour) stopTour();
    const v = viewFor(allIds(), 1.15) || { target: new THREE.Vector3(), radius: 600 };
    fly({ ...v, theta: kind === 'bird' ? 0.8 : cam.theta, phi: kind === 'top' ? 0.04 : kind === 'side' ? 1.5 : 0.95 }, 1600);
  }
  function flyToActive(tourMode) {
    const set = store.activeSet(); if (!set) return;
    const v = viewFor([...set]); if (!v) return;
    fly({ ...v, theta: cam.theta + (tourMode ? 0.9 : 0.35), phi: tourMode ? 1.05 : Math.min(1.25, Math.max(0.7, cam.phi)) }, tourMode ? 1900 : 1400);
  }

  // ---------- picking
  const v3 = new THREE.Vector3();
  function pick(mx, my) {
    let best = -1, bd = 196;
    for (let i = 0; i < nodes.length; i++) {
      if (pinfo[i]?.cg && !pinfo[i].first) continue;
      if (curSet && !curSet.has(nodes[i].id) && !store.hover) { /* still pickable */ }
      v3.set(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]).applyMatrix4(world.matrixWorld).project(camera);
      if (v3.z > 1) continue;
      const sx = (v3.x * 0.5 + 0.5) * W, sy = (-v3.y * 0.5 + 0.5) * H;
      const d = (sx - mx) ** 2 + (sy - my) ** 2;
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  }
  // FR-1063 AC-346: 層ごとの領域ラベル（▾/▸・名称・件数）を押すと、下位の点を畳む／開く。キーボードではパネルの木が同じ状態を操作する。
  function pickLabel(mx, my) {
    for (const h of labelHits) {
      v3.copy(h.pos).applyMatrix4(world.matrixWorld).project(camera);
      if (v3.z > 1) continue;
      const sx = (v3.x * 0.5 + 0.5) * W, sy = (-v3.y * 0.5 + 0.5) * H;
      if (Math.abs(sx - mx) < 80 && Math.abs(sy - my) < 14) return h;
    }
    return null;
  }
  const cvs = renderer.domElement;
  cvs.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY, px: e.clientX, py: e.clientY, pan: e.button === 2 || e.shiftKey }; moved = false; cvs.setPointerCapture(e.pointerId); stopTour(); anim = null; lastInput = performance.now(); });
  cvs.addEventListener('contextmenu', (e) => e.preventDefault());
  cvs.addEventListener('pointermove', (e) => {
    lastInput = performance.now();
    const r = cvs.getBoundingClientRect();
    if (drag) {
      const dx = e.clientX - drag.px, dy = e.clientY - drag.py; drag.px = e.clientX; drag.py = e.clientY;
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 3) moved = true;
      if (drag.pan) {
        const k = cam.radius * 0.0016, right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0), up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
        cam.target.addScaledVector(right, -dx * k).addScaledVector(up, dy * k);
      } else { cam.vt = -dx * 0.005; cam.vp = -dy * 0.005; cam.theta += cam.vt; cam.phi = Math.min(3.05, Math.max(0.03, cam.phi + cam.vp)); }
      hideTip(); return;
    }
    const i = pick(e.clientX - r.left, e.clientY - r.top);
    cvs.style.cursor = i >= 0 || pickLabel(e.clientX - r.left, e.clientY - r.top) ? 'pointer' : 'grab';
    store.setHover(i >= 0 ? nodes[i].id : null);
    if (i >= 0) showTip(nodeTip(nodes[i]), e.clientX, e.clientY); else hideTip();
  });
  cvs.addEventListener('pointerup', (e) => {
    const was = moved; drag = null; if (was) return;
    const r = cvs.getBoundingClientRect(), i = pick(e.clientX - r.left, e.clientY - r.top);
    if (i >= 0) { const cg = pinfo[i]?.cg; if (cg) tierState.setOpen(cg.tier, true, 'map'); else store.select(nodes[i].id, { fly: true }); return; }
    if (store.activeSet()) store.clear();
  });
  cvs.addEventListener('pointerleave', () => { store.setHover(null); hideTip(); });
  // 領域のラベルはダブルクリックで畳む／開く（1 回の押下は点の選択に使う）。キーボードはパネルの木。
  cvs.addEventListener('dblclick', (e) => {
    const r = cvs.getBoundingClientRect(), lh = pickLabel(e.clientX - r.left, e.clientY - r.top);
    if (lh) { tierState.toggle(lh.tier, 'map'); return; }
    store.clear(); bird();
  });
  cvs.addEventListener('wheel', (e) => { e.preventDefault(); stopTour(); anim = null; lastInput = performance.now(); cam.radius = Math.min(4000, Math.max(20, cam.radius * Math.exp(e.deltaY * 0.0012))); }, { passive: false });
  // キーボードでのカメラ操作（矢印＝回す、+ / − ＝拡大縮小）。手動操作なので、プリセットの自動動作は止まる（camera3d.js が検知）。
  cvs.addEventListener('keydown', (e) => {
    const k = e.key; let used = true;
    if (k === 'ArrowLeft') cam.theta -= 0.12; else if (k === 'ArrowRight') cam.theta += 0.12;
    else if (k === 'ArrowUp') cam.phi = Math.max(0.03, cam.phi - 0.08); else if (k === 'ArrowDown') cam.phi = Math.min(3.05, cam.phi + 0.08);
    else if (k === '+' || k === '=') cam.radius = Math.max(20, cam.radius * 0.89); else if (k === '-') cam.radius = Math.min(4000, cam.radius * 1.12);
    else used = false;
    if (used) { e.preventDefault(); stopTour(); anim = null; lastInput = performance.now(); }
  });

  // ---------- tour
  function stopTour() { if (tour) { clearTimeout(tour.timer); tour = null; renderToolbar(); } }
  function startTour() {
    if (tour) return stopTour();
    const goals = nodes.filter((n) => n.type === 'goal').map((n) => n.id);
    const seq = goals.length ? goals : nodes.filter((n) => n.type === 'req').slice(0, 6).map((n) => n.id);
    let i = 0; tour = { timer: 0 };
    const next = () => {
      if (!tour) return;
      if (i >= seq.length) { store.clear(); bird('bird', true); tour.timer = setTimeout(stopTour, 2400); return; }
      store.select(seq[i++], { fly: true, tour: true });
      tour.timer = setTimeout(next, 4600);
    };
    store.clear(); bird('bird', true); tour.timer = setTimeout(next, 1800); renderToolbar();
  }

  // ---------- chrome
  function renderToolbar() {
    toolbar.replaceChildren(
      el('div', { class: 'grp' },
        el('button', { onclick: () => bird('bird') }, '🛰 ' + t('map.bird')),
        el('button', { onclick: () => bird('side') }, '▤ ' + t('map3d.side')),
        el('button', { onclick: () => bird('top') }, '◎ ' + t('map3d.top')),
        el('button', { onclick: () => { stopTour(); flyToActive(); } }, icon('goal', { size: 16 }), ' ' + t('map.zoomsel')),
        el('button', { class: tour ? 'on' : '', onclick: startTour }, (tour ? '■ ' : '▶ ') + t('map.tour')),
        el('button', { class: prefs.auto ? 'on' : '', onclick: () => { prefs.auto = !prefs.auto; renderToolbar(); } }, '⟳ ' + t('map3d.auto'))),
      el('details', { class: 'grp pop' }, el('summary', {}, '◧ ' + t('map.layers')), el('div', {}, LAYER_TYPES.map((ty) => el('label', {},
        el('input', { type: 'checkbox', checked: prefs.layers.has(ty) || null, onchange: (e) => { e.target.checked ? prefs.layers.add(ty) : prefs.layers.delete(ty); rebuild(); } }),
        el('i', { class: 'dot', style: { background: TYPE_COLOR[ty] } }), t('type.' + ty))))),
      el('div', { class: 'grp' }, ['type', 'status', 'impl'].map((m) => el('button', { class: prefs.color === m ? 'on' : '', onclick: () => { prefs.color = m; rebuild(true); } }, t('map.color.' + m)))));
    hint.textContent = t('map3d.hint');
  }
  function renderStatus() {
    const set = store.activeSet();
    statusBox.hidden = !set;
    if (!set) return;
    const n = store.selected ? store.node(store.selected) : null;
    statusBox.replaceChildren(
      el('div', {}, n ? el('b', {}, n.label) : el('b', {}, store.focusLabel || t('focus.set')), ' · ', t('focus.count', { n: [...set].filter((id) => idx.has(id)).length })),
      el('div', { class: 'row', style: { marginTop: '6px' } }, el('button', { class: 'btn ghost', onclick: () => store.clear() }, t('focus.clear'))));
  }
  function rebuild(keep) { build(); renderToolbar(); renderStyleToggle(); if (!keep) bird(); }

  function resize() {
    const r = mount3.getBoundingClientRect();
    W = Math.max(1, r.width); H = Math.max(1, r.height);
    renderer.setSize(W, H, true);
    camera.aspect = W / H; camera.updateProjectionMatrix();
    nodeMat.uniforms.uScale.value = (H * renderer.getPixelRatio()) / (2 * Math.tan((camera.fov * Math.PI) / 360));
  }
  const ro = new ResizeObserver(resize); ro.observe(host); ro.observe(mount3);
  resize();
  build(); renderToolbar(); renderStyleToggle();
  const snapshot = document.documentElement.classList.contains('snapshot');
  {
    const v = viewFor(allIds(), 1.15);
    if (v) { cam.target.copy(v.target); cam.radius = v.radius * 1.5; }
    if (snapshot) {
      cam.theta = 0.8; cam.phi = 0.95; placeCamera();
    } else {
      fly({ ...(v || {}), theta: 0.8, phi: 0.95 }, 2200);
    }
  }
  if (store.activeSet() && !snapshot) setTimeout(() => flyToActive(), 300);

  const offs = [
    store.on('select', (o) => {
      const n = o.id && store.node(o.id);
      if (n && !idx.has(n.id) && LAYER_TYPES.includes(n.type) && !prefs.layers.has(n.type)) { prefs.layers.add(n.type); rebuild(true); }
      const cgp = o.id && idx.has(o.id) ? pinfo[idx.get(o.id)]?.cg : null;
      if (cgp) { tierState.setOpen(cgp.tier, true, 'map'); }      // 畳んだ領域の点が選ばれたら、領域を開く（開くと再構築される）
      applyHighlight();
      if (o.cleared) return;
      if (o.fly || o.focus) flyToActive(!!o.tour);
    }),
    store.on('hover', () => applyHighlight()),
    store.on('model', () => rebuild()),
    tierState.on(() => rebuild(true)),
    onLang(() => { rebuild(true); rig.refresh(); }),
  ];

  // ---------- loop
  const clock = performance.now();
  function frame(now) {
    if (!snapshot) raf = requestAnimationFrame(frame);
    if (dead) return;
    stepAnim(now);
    if (!drag) { cam.theta += cam.vt; cam.vt *= 0.92; cam.phi = Math.min(3.05, Math.max(0.03, cam.phi + cam.vp)); cam.vp *= 0.92; }
    if (prefs.auto && !rig.auto() && !anim && !drag && !tour && now - lastInput > 5000) cam.theta += 0.0016;
    if (tour && !anim) cam.theta += 0.004;
    placeCamera();
    // pulse the selected node and move particles
    if (pointsObj && store.selected && idx.has(store.selected)) {
      const i = idx.get(store.selected), sz = pointsObj.geometry.attributes.size;
      sz.array[i] = pointsObj.userData.base[i] * (1.9 + 0.35 * Math.sin(now / 200)); sz.needsUpdate = true;
    }
    if (parts && parts.userData.edges.length) {
      const arr = parts.geometry.attributes.position.array, ed = parts.userData.edges;
      for (let k = 0; k < ed.length; k++) {
        const [a, b, ph] = ed[k], f = ((now / 1800) + ph) % 1;
        arr[k * 3] = P[a * 3] + (P[b * 3] - P[a * 3]) * f; arr[k * 3 + 1] = P[a * 3 + 1] + (P[b * 3 + 1] - P[a * 3 + 1]) * f; arr[k * 3 + 2] = P[a * 3 + 2] + (P[b * 3 + 2] - P[a * 3 + 2]) * f;
      }
      parts.geometry.attributes.position.needsUpdate = true;
    }
    // keep static labels readable: shrink when the camera is very close
    refreshShapes(now);
    renderer.render(scene, camera);
  }
  // FR-1063 AC-346: 画面に見える状態の公開（2D と同じ形。x・y は画面座標）。畳まれた領域の点は visible=false。
  const viewApi3 = {
    mode: 'map3d',
    getState: () => {
      const rc = cvs.getBoundingClientRect(), pts = [], q = new THREE.Vector3();
      nodes.forEach((n, i) => {
        const tp = tierPathOf(n); if (!tp) return;
        q.set(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]).applyMatrix4(world.matrixWorld).project(camera);
        pts.push({ id: n.id, kind: tp[0], division: tp[1], area: tp[2], x: rc.left + (q.x * 0.5 + 0.5) * W, y: rc.top + (-q.y * 0.5 + 0.5) * H, visible: !pinfo[i]?.cg });
      });
      return { mode: 'map3d', map3d: { points: pts, tiers: JSON.parse(mount3.dataset.tiers || '[]') } };
    },
  };
  window.eabkView = viewApi3;
  // FR-1068 AC-374: テスト hook。いま描かれているノードの {id, kind, shape}。
  const hook3 = { nodes: displayedNodes, style: () => prefs.style, fx: () => [...fxSet()], camera: () => rig.camera() };
  window.__eabk3d = hook3;
  if (snapshot) frame(0);
  else raf = requestAnimationFrame(frame);
  if (snapshot) {
    host.append(el('section', { class: 'snapshot-3d card' },
      el('h2', {}, '3D レイヤー構成'),
      el('p', {}, '目的 → 要求 → Entity / API / Table → 実装ファイル → System Test'),
      el('div', { class: 'chips' }, [...store.nodes.values()].slice(0, 36).map((node) =>
        el('span', { class: 'badge' }, `${node.id}: ${node.label}`)))));
  }

  return {
    destroy() {
      if (window.eabkView === viewApi3) window.eabkView = undefined;
      if (window.__eabk3d === hook3) delete window.__eabk3d;
      dead = true; cancelAnimationFrame(raf); stopTour(); rig.destroy(); rig.el.remove(); ro.disconnect(); offs.forEach((f) => f()); hideTip();
      scene.traverse((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
      labelCache.forEach((tx) => tx.dispose());
      renderer.dispose(); renderer.forceContextLoss?.();
    },
  };
}

// NFR-UX-015 AC-390: 3D（WebGL）を描画できない環境の代替。理由・2D への導線・種別とかたちの表を出し、選択（store）は触らない。
function mountNoWebgl(host) {
  host.replaceChildren();
  const rows = LAYER_TYPES.map((k) => el('tr', {}, el('th', { scope: 'row' }, kindName(k)), el('td', {}, shapeName(shapeOf(k)))));
  host.append(el('section', { class: 'card nowebgl', 'data-testid': 'dim-fallback', role: 'alert' },
    el('h2', {}, t('cam3d.nowebgl.h')), el('p', {}, t('dim.nowebgl')), el('p', { class: 'mini' }, t('cam3d.nowebgl.d')),
    el('a', { class: 'btn', href: '#/map2d' }, t('sz.to2d')),
    el('table', { 'data-testid': 'legend-table' }, el('thead', {}, el('tr', {}, el('th', {}, t('cam3d.nowebgl.kind')), el('th', {}, t('cam3d.nowebgl.shape')))), el('tbody', {}, rows))));
  setTimeout(() => publishDim({ dims: ['2d', '3d', 'rpg', 'graph'], current: '2d', selected: '3d' }), 0);   // 選んだのは 3D のまま（元の選択を保つ）
  return { destroy() {} };
}

// FR-1027..FR-1029: when the model has entity relations or columns, this route opens the entity view (semantic zoom) first;
// the classic relationship graph stays one button away.  The target, level and filter are shared with the other renderer.
export function mount(host) {
  let inner = null, tiers = null;
  const run = () => {
    inner?.destroy?.();
    tiers?.destroy?.();
    host.replaceChildren();
    if (isArch() || wantsEntityView(store.model)) {
      inner = mountShell(host, { mode: 'map3d', createRenderer: create3d,
        links: [{ id: 'sz-to-2d', label: () => t('sz.to2d'), href: '#/map2d' + (isArch() ? '?view=arch' : '') },
          isArch() ? { id: 'sz-to-entity', label: () => t('arch.toentity'), href: '#/map3d' } : { id: 'sz-to-arch', label: () => t('arch.toarch'), href: '#/=arch' }], onSwitch: () => { setTab('graph'); run(); } });
    } else {
      try { inner = mountGraph(host); }
      catch (e) { inner = mountNoWebgl(host); }   // NFR-UX-015 AC-390: WebGL が無い環境では、エラーにせず 2D と理由・表を示す
      if (hasEntityStructure(store.model)) host.append(el('button', { type: 'button', class: 'btn ghost sz-switch', onclick: () => { setTab('entities'); run(); } }, t('sz.entview')));
    }
    tiers = mountMapTiers(host, 'map3d');   // FR-1063: 上位層（種類→区分→領域→項目）
  };
  run();
  return { destroy() { inner?.destroy?.(); tiers?.destroy?.(); } };
}