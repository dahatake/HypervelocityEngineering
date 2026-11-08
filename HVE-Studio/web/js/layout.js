// NFR-UX-002 AC-015 / AC-041: 画面の配置（レイアウト）。
// 保存するのは配置の識別子だけ（検索語・選択対象・絞り込みは保存しない）。保存先はブラウザーの localStorage で、
// 別のブラウザー・端末には引き継がれない。壊れた保存値・未知の値は既定（default）に戻す（エラーにしない）。
// 配置の変更・既定へ戻す操作は再読込なしで行え、画面の状態（検索語・選択・絞り込み）には触れない。
export const LAYOUT_KEY = 'eabk-studio.layout';
export const LAYOUTS = ['default', 'compact', 'wide'];
export const DEFAULT_LAYOUT = 'default';

function load() {
  try {
    const v = window.localStorage.getItem(LAYOUT_KEY);
    return LAYOUTS.includes(v) ? v : DEFAULT_LAYOUT; // '{broken' など不正値は既定
  } catch { return DEFAULT_LAYOUT; }
}
let id = load();
const listeners = new Set();

function apply() {
  document.documentElement.setAttribute('data-layout', id);
  listeners.forEach((fn) => { try { fn(layoutState()); } catch (e) { console.error(e); } });
}
export const layoutState = () => ({ id, isDefault: id === DEFAULT_LAYOUT });
export function setLayout(next) {
  if (!LAYOUTS.includes(next) || next === id) return;
  id = next;
  try {
    if (id === DEFAULT_LAYOUT) window.localStorage.removeItem(LAYOUT_KEY); else window.localStorage.setItem(LAYOUT_KEY, id);
  } catch { /* 保存できなくても表示は変える */ }
  apply();
}
// 既定でない別の配置へ順に切り替える（default → compact → wide → compact …）。
export function changeLayout() {
  const others = LAYOUTS.filter((l) => l !== DEFAULT_LAYOUT);
  setLayout(others[(others.indexOf(id) + 1) % others.length]);
}
export const resetLayout = () => setLayout(DEFAULT_LAYOUT); // 既に既定なら何も変えない
export const onLayout = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

// window.eabkView: 画面共通のアクセサ。各画面（map など）が代入した view を公開し、getState().layout を常に付ける。
// 画面を離れたら undefined を代入する（基底の view に戻る）。
const base = { getState: () => ({}) };
let screen;
function withLayout(v) {
  if (v && !v.__layoutWrapped) {
    const orig = typeof v.getState === 'function' ? v.getState.bind(v) : () => ({});
    try { v.getState = () => ({ ...orig(), layout: layoutState() }); Object.defineProperty(v, '__layoutWrapped', { value: true }); } catch { /* frozen */ }
  }
  return v;
}
base.getState = () => ({ layout: layoutState() });
Object.defineProperty(window, 'eabkView', {
  configurable: true,
  get: () => screen || base,
  set: (v) => { screen = v ? withLayout(v) : undefined; },
});

apply();
