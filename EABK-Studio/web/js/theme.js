/* テーマの解決（FR-1047）。最初の描画の前に同期で実行して、ちらつきを防ぐ。
   選択は light / dark / system の 3 択で、既定は system（OS の配色設定に従い、OS 側の変更に再読込なしで追従する）。
   選択は保存しない（AC-260）: 開くたびに system から始まり、利用者の選択はそのセッション中だけ有効。 */
(function () {
  var root = document.documentElement;
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  var choice = 'system';
  var listeners = [];
  function resolved() { return choice === 'system' ? (mq.matches ? 'dark' : 'light') : choice; }
  function apply() {
    root.setAttribute('data-theme-choice', choice);
    root.setAttribute('data-theme', resolved());
    listeners.forEach(function (fn) { try { fn(choice, resolved()); } catch (e) { console.error(e); } });
  }
  var onOs = function () { if (choice === 'system') apply(); };
  if (mq.addEventListener) mq.addEventListener('change', onOs); else if (mq.addListener) mq.addListener(onOs);
  window.eabkTheme = {
    choices: ['light', 'dark', 'system'],
    get: function () { return choice; },
    resolved: resolved,
    set: function (c) { if (this.choices.indexOf(c) < 0) return; choice = c; apply(); },
    onChange: function (fn) { listeners.push(fn); },
  };
  apply();
})();
