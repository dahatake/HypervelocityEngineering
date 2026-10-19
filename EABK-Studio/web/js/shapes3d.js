// FR-1068 / FR-1069: 3D のノードの「種別 → かたち」の対応表（1 か所）と、かたちの組立て・凡例・演出スタイル。
// 凡例・3D の描画（map3d.js）・テストは、すべてこの SHAPE_OF を参照する。かたちは three.js の標準ジオメトリの組合せだけで作り、
// 外部のモデル・テクスチャ・フォントは使わない。保存するのは演出スタイル名（文字列）だけ（FR-1069 AC-380 / NFR-SEC-003）。
import * as THREE from 'three';
import { t } from './i18n.js';
import { el } from './ui.js';

// ---- 種別名 → かたちの識別（data-shape）。ここだけを書き換えれば、凡例も 3D も追従する。
export const SHAPE_OF = Object.freeze({
  goal: 'crystal',      // 目的（G-ID）: 結晶（八面体）
  req: 'scroll',        // 要求: 巻物
  nfr: 'scroll',
  ac: 'prism',          // 受入基準: 四面体
  entity: 'block',      // エンティティ: ブロック
  part: 'gear',         // 共通部品・コンポーネント: 歯車
  component: 'gear',
  api: 'gate',          // API: ゲート
  table: 'database',    // テーブル: 円柱を重ねたデータベース
  param: 'knob',        // パラメーター: つまみ（トーラス）
  question: 'pawn',     // 質問: 円錐＋球
  file: 'sheet',        // ファイル: 薄板
  test: 'sheet',
  case: 'flask',        // 試験ケース: フラスコ
  screen: 'display',    // 画面: ディスプレイ板
  module: 'module',     // モジュール: 十二面体
  state: 'signal',      // 状態: 信号灯
  persona: 'person',    // ペルソナ（人）: 頭＋胴のシルエット
  system: 'building',   // 対象システム: 建物（ボックス群）
  external: 'cloud',    // 外部連携: プラグ付きの雲
  integration: 'cloud',
});
export const DEFAULT_SHAPE = 'default';
export const shapeOf = (kind) => SHAPE_OF[kind] || DEFAULT_SHAPE;
export const isKnownKind = (kind) => Object.prototype.hasOwnProperty.call(SHAPE_OF, kind);
export const SHAPE_IDS = [...new Set([...Object.values(SHAPE_OF), DEFAULT_SHAPE])];

// ---- かたちの定義: 部品（標準ジオメトリ）の組合せ。単位は「半径 1 程度」。
const G = {
  oct: new THREE.OctahedronGeometry(1.1), tet: new THREE.TetrahedronGeometry(1.1), dod: new THREE.DodecahedronGeometry(1),
  sph: new THREE.SphereGeometry(0.85, 14, 10), sphS: new THREE.SphereGeometry(0.45, 12, 8),
  box: new THREE.BoxGeometry(1.5, 1.5, 1.5), cyl: new THREE.CylinderGeometry(1, 1, 0.6, 16),
  tor: new THREE.TorusGeometry(0.75, 0.28, 8, 18), torS: new THREE.TorusGeometry(0.6, 0.22, 8, 16),
  pole: new THREE.CylinderGeometry(0.16, 0.16, 2.2, 8), pillar: new THREE.BoxGeometry(0.4, 2, 0.4), lintel: new THREE.BoxGeometry(2.2, 0.4, 0.4),
  sheet: new THREE.BoxGeometry(1.5, 2, 0.18), fold: new THREE.BoxGeometry(0.5, 0.5, 0.22), roll: new THREE.CylinderGeometry(0.28, 0.28, 2, 10),
  disp: new THREE.BoxGeometry(2.3, 1.5, 0.16), stand: new THREE.CylinderGeometry(0.12, 0.12, 0.8, 8), base: new THREE.BoxGeometry(1, 0.1, 0.5),
  torso: new THREE.CylinderGeometry(0.55, 0.85, 1.4, 12), tower: new THREE.BoxGeometry(1.0, 2.2, 1.0), wing: new THREE.BoxGeometry(0.8, 1.2, 0.9),
  plugBody: new THREE.BoxGeometry(0.6, 0.5, 0.4), prong: new THREE.CylinderGeometry(0.05, 0.05, 0.4, 6),
  cone: new THREE.ConeGeometry(0.85, 1.4, 14), coneDown: new THREE.ConeGeometry(1, 1.3, 14), neck: new THREE.CylinderGeometry(0.28, 0.28, 0.9, 10),
};
const Q = (x, y, z) => new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z));
const part = (geo, x = 0, y = 0, z = 0, q = null, s = 1) => ({ geo, m: new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), q || new THREE.Quaternion(), new THREE.Vector3(s, s, s)) });
export const SHAPE_PARTS = {
  crystal: [part(G.oct, 0, 0, 0, null, 1.15)],
  scroll: [part(G.sheet, 0, 0, 0, null, 0.9), part(G.roll, -0.8, 0, 0, null, 0.9), part(G.roll, 0.8, 0, 0, null, 0.9)],
  prism: [part(G.tet, 0, 0, 0, null, 1.05)],
  block: [part(G.box, 0, 0, 0, null, 0.85)],
  gear: [part(G.cyl, 0, 0, 0, Q(Math.PI / 2, 0, 0), 0.95), part(G.tor, 0, 0, 0, null, 1.1), part(G.box, 1.05, 0, 0, null, 0.3), part(G.box, -1.05, 0, 0, null, 0.3), part(G.box, 0, 1.05, 0, null, 0.3), part(G.box, 0, -1.05, 0, null, 0.3)],
  gate: [part(G.pillar, -0.9, 0, 0), part(G.pillar, 0.9, 0, 0), part(G.lintel, 0, 1.1, 0)],
  database: [part(G.cyl, 0, -0.75, 0), part(G.cyl, 0, 0, 0), part(G.cyl, 0, 0.75, 0)],
  knob: [part(G.tor, 0, 0, 0, null, 1.1), part(G.sphS, 0, 0, 0, null, 0.7)],
  pawn: [part(G.cone, 0, -0.35, 0, null, 0.9), part(G.sphS, 0, 0.85, 0, null, 1.05)],
  sheet: [part(G.sheet, 0, 0, 0, null, 0.95), part(G.fold, 0.55, 0.85, 0.02, null, 0.9)],
  flask: [part(G.coneDown, 0, -0.45, 0, Q(Math.PI, 0, 0), 1), part(G.neck, 0, 0.7, 0)],
  display: [part(G.disp, 0, 0.35, 0, null, 0.9), part(G.stand, 0, -0.65, 0), part(G.base, 0, -1.05, 0, null, 1.6)],
  module: [part(G.dod, 0, 0, 0, null, 1.05)],
  signal: [part(G.pole, 0, 0, 0, null, 0.9), part(G.sph, 0, 0.9, 0, null, 0.8)],
  person: [part(G.sph, 0, 0.95, 0, null, 0.7), part(G.torso, 0, -0.35, 0, null, 1)],
  building: [part(G.tower, 0, 0.1, 0, null, 1), part(G.wing, -1.0, -0.4, 0, null, 1), part(G.wing, 1.0, -0.4, 0, null, 1)],
  cloud: [part(G.sph, -0.7, -0.1, 0, null, 0.8), part(G.sph, 0.1, 0.3, 0, null, 1), part(G.sph, 0.8, -0.1, 0, null, 0.75),
    part(G.plugBody, 0, -1.0, 0, null, 1), part(G.prong, -0.15, -1.4, 0, null, 1), part(G.prong, 0.15, -1.4, 0, null, 1)],
  default: [part(G.sph, 0, 0, 0, null, 1.1)],
};

// ---- 演出スタイル（保存はスタイル名だけ。使えない保存先ではエラーにせず既定で動く）
export const STYLES = ['engineering', 'entertainment'];
export const DEFAULT_STYLE = 'engineering';
export const STYLE_KEY = 'eabk-studio.style3d';
export const FX_BY_STYLE = { engineering: [], entertainment: ['glow', 'float', 'particles'] };
export const normStyle = (v) => (STYLES.includes(v) ? v : DEFAULT_STYLE);
export function loadStyle() { try { return normStyle(window.localStorage.getItem(STYLE_KEY)); } catch (e) { return DEFAULT_STYLE; } }
export function saveStyle(v) { try { window.localStorage.setItem(STYLE_KEY, normStyle(v)); } catch (e) { /* 保存できなくても動く */ } }

// ---- 凡例: 種別ごとに「かたちの小さな図（SVG）・種別名・かたちの語」の 1 行。
const SW = {
  crystal: '<path d="M12 2l8 10-8 10-8-10z"/>', scroll: '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9 8h6M9 12h6"/>',
  prism: '<path d="M12 3l9 17H3z"/>', block: '<rect x="5" y="5" width="14" height="14"/>',
  gear: '<circle cx="12" cy="12" r="6"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>', gate: '<path d="M5 21V8h14v13M5 8h14"/><path d="M9 21V12h6v9"/>',
  database: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3 3 7 3s7-1.3 7-3"/>',
  knob: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>', pawn: '<path d="M12 9l6 12H6z"/><circle cx="12" cy="6" r="3"/>',
  sheet: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>', flask: '<path d="M10 3h4M10 3v6l-5 11h14l-5-11V3"/>',
  display: '<rect x="3" y="4" width="18" height="12" rx="1"/><path d="M9 20h6M12 16v4"/>', module: '<path d="M12 2l9 6v8l-9 6-9-6V8z"/>',
  signal: '<path d="M12 12v10"/><circle cx="12" cy="8" r="5"/>',
  person: '<circle cx="12" cy="7" r="4"/><path d="M5 21c0-5 3-8 7-8s7 3 7 8z"/>',
  building: '<path d="M8 21V3h8v18M3 21V11h5M16 21V11h5M3 21h18"/>',
  cloud: '<path d="M7 16a4 4 0 010-8 5 5 0 019-1 4 4 0 011 9z"/><path d="M10 16v5M14 16v5"/>', default: '<circle cx="12" cy="12" r="8"/>',
};
export function shapeSwatch(shape, color = 'currentColor') {
  const w = document.createElement('span');
  w.innerHTML = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true" data-shape="${shape}">${SW[shape] || SW.default}</svg>`;
  return w.firstChild;
}
export const kindName = (kind) => (isKnownKind(kind) ? tKind(kind) : t('shape3d.other'));
function tKind(kind) { const k = 'type.' + kind; const v = t(k); return v === k ? kind : v; }
export const shapeName = (shape) => t('shape3d.' + shape);

// kinds: [{kind, color, count}]。onFocus(kind|null) は凡例の項目を選んだときの強調。
export function buildLegend(kinds, { focus = null, onFocus = () => {} } = {}) {
  const rows = kinds.map(({ kind, color, count }) => {
    const shape = shapeOf(kind), on = focus === kind;
    const btn = el('button', { type: 'button', class: 'legend-row' + (on ? ' on' : ''), 'data-kind': kind, 'data-shape-id': shape, 'aria-pressed': String(on), title: `${kindName(kind)} · ${shapeName(shape)}`,
      onclick: () => onFocus(on ? null : kind) },
    shapeSwatch(shape, color), el('span', { class: 'lg-name' }, kindName(kind)), el('span', { class: 'lg-shape' }, shapeName(shape)), el('span', { class: 'lg-n' }, String(count)));
    return btn;
  });
  return el('div', { class: 'legend3d', 'data-testid': 'legend-3d', role: 'group', 'aria-label': t('legend3d.title') },
    el('div', { class: 'lg-title' }, t('legend3d.title')), ...rows);
}

// ---- 演出スタイルの切替（3D 画面の中に置く。ヘッダーのコントロールには触れない）
export function buildStyleToggle(current, onPick) {
  return el('div', { class: 'style3d', 'data-testid': 'style-toggle', 'data-current': current, role: 'group', 'aria-label': t('style3d.label') },
    el('span', { class: 'st-label' }, t('style3d.label')),
    ...STYLES.map((v) => el('button', { type: 'button', class: v === current ? 'on' : '', 'data-style-value': v, 'aria-pressed': String(v === current), onclick: () => onPick(v) }, t('style3d.' + v))));
}

// ---- ノードのオブジェクト群（かたちごと・部品ごとの InstancedMesh）
// items: [{ kind, x, y, z, size, color(THREE.Color), hidden }]。apply() が強調・浮遊・発光を毎フレーム反映する。
export function buildNodeObjects(items) {
  const group = new THREE.Group();
  const byShape = new Map();
  items.forEach((it, i) => { const s = shapeOf(it.kind); if (!byShape.has(s)) byShape.set(s, []); byShape.get(s).push(i); });
  const meshes = [];
  const mat = () => new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.15, emissive: 0x000000 });
  for (const [shape, list] of byShape) {
    for (const p of SHAPE_PARTS[shape]) {
      const m = new THREE.InstancedMesh(p.geo, mat(), list.length);
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      m.frustumCulled = false; m.userData = { list, part: p, shape };
      group.add(m); meshes.push(m);
    }
  }
  const tmp = new THREE.Matrix4(), tmp2 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), pos = new THREE.Vector3(), col = new THREE.Color(), bg = new THREE.Color(0x0b1020);
  // state: { dim:(i)=>bool, grow:(i)=>number, selected:index|-1, focusKind, now, fx:Set, spin }
  function apply(state) {
    const fx = state.fx || new Set();
    for (const m of meshes) {
      const { list, part: pt } = m.userData;
      list.forEach((gi, k) => {
        const it = items[gi];
        const on = !(state.dim && state.dim(gi)) && (!state.focusKind || state.focusKind === it.kind);
        let s = it.hidden ? 0.0001 : it.size * (state.grow ? state.grow(gi) : 1) * (on ? 1 : 0.8);
        if (gi === state.selected) s *= 1.5 + (fx.has('glow') ? 0.1 * Math.sin(state.now / 200) : 0);
        const yOff = fx.has('float') ? Math.sin(state.now / 700 + gi * 0.7) * 1.4 : 0;
        const rot = fx.has('float') ? state.now / 2500 + gi : 0;
        q.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, rot);
        pos.set(it.x, it.y + yOff, it.z); sc.set(s, s, s);
        tmp.compose(pos, q, sc);
        tmp2.multiplyMatrices(tmp, pt.m);
        m.setMatrixAt(k, tmp2);
        const dimmed = !on;
        col.copy(it.color); if (dimmed) col.lerp(bg, 0.85);
        m.setColorAt(k, col);
      });
      m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true;
      m.material.emissive.setHex(fx.has('glow') ? 0x223355 : 0x000000);
      m.material.emissiveIntensity = fx.has('glow') ? 0.6 + 0.4 * Math.sin(state.now / 600) : 0;
    }
  }
  return { group, apply, dispose() { for (const m of meshes) { m.material.dispose(); m.dispose?.(); } } };
}

export function addSceneLights(scene) {
  const amb = new THREE.AmbientLight(0xffffff, 1.1), dir = new THREE.DirectionalLight(0xffffff, 2.2);
  dir.position.set(0.6, 1, 0.8);
  scene.add(amb, dir);
  return [amb, dir];
}
