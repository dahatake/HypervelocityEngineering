// hve/gui/widgets/xterm_assets/bridge.js — Python ↔ JS 双方向ブリッジ。
//
// 仕様:
//   - QWebChannel 経由で `py_bridge` オブジェクトに接続する。
//   - py_bridge.feed_output_b64(b64) を呼び出すと、PTY 出力 (生バイト列を base64 化したもの)
//     を xterm.js のターミナルへ書き込む。
//   - ユーザー入力は xterm.onData() で文字列を受け取り、UTF-8 → base64 化して
//     py_bridge.user_input_b64(b64) を呼び出す。
//   - FitAddon でコンテナサイズへフィットさせ、cols/rows 変更時に
//     py_bridge.resized(cols, rows) を通知する。
//   - 初期化完了後に py_bridge.notify_ready() を 1 度だけ呼ぶ。
//
// バイナリ運搬: QWebChannel は JSON-serializable な値のみを運ぶため、生バイト列は
// base64 で授受する。改行 (\n / \r\n) や ANSI エスケープ (\x1b[...) はそのまま透過する。

(function () {
  "use strict";

  const term = new Terminal({
    cursorBlink: true,
    convertEol: false,        // CR/LF はサーバ側の出力をそのまま尊重
    fontFamily: 'Consolas, "Cascadia Mono", "Courier New", monospace',
    fontSize: 13,
    scrollback: 5000,
    theme: {
      background: "#1e1e1e",
      foreground: "#d4d4d4",
      cursor: "#d4d4d4",
    },
    allowProposedApi: true,
  });

  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);

  const container = document.getElementById("term");
  term.open(container);

  // 外部 (Python の runJavaScript) から参照可能にするため window へ露出。
  // 機密データを保持しないため XSS 危険性は CSP + ローカル限定で抑止。
  window.term = term;
  window.fitAddon = fitAddon;

  function safeFit() {
    try {
      fitAddon.fit();
    } catch (e) {
      // 初期化途中などで失敗することがあるため握りつぶす
    }
  }
  safeFit();

  // ----- base64 helpers (UTF-8 安全) -----
  function bytesToBase64(uint8) {
    let s = "";
    const chunk = 0x8000;
    for (let i = 0; i < uint8.length; i += chunk) {
      s += String.fromCharCode.apply(null, uint8.subarray(i, i + chunk));
    }
    return btoa(s);
  }

  function base64ToBytes(b64) {
    const s = atob(b64);
    const len = s.length;
    const out = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      out[i] = s.charCodeAt(i);
    }
    return out;
  }

  function utf8Encode(str) {
    return new TextEncoder().encode(str);
  }

  function utf8Decode(bytes) {
    return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
  }

  // ----- QWebChannel 接続 -----
  function attachBridge(bridge) {
    // Python 側 (_PyBridge) の Slot/Signal:
    //   Slots (JS → Python):  user_input_b64(b64), report_resize(cols, rows), notify_ready()
    //   Signals (Python → JS): output_b64(str), terminal_cleared()

    function sendInputBytes(bytes) {
      const b64 = bytesToBase64(bytes);
      bridge.user_input_b64(b64);
    }

    term.onData((data) => {
      // data は string (xterm が VT100 シーケンスに整形済み)
      sendInputBytes(utf8Encode(data));
    });

    // バイナリ入力 (xterm の onBinary は raw 1-byte string)
    if (term.onBinary) {
      term.onBinary((data) => {
        const bytes = new Uint8Array(data.length);
        for (let i = 0; i < data.length; i++) bytes[i] = data.charCodeAt(i) & 0xff;
        sendInputBytes(bytes);
      });
    }

    // PTY 出力 (Python 側から呼ばれるメソッドは Python 側オブジェクトのスロット。
    // JS からは Python 側を呼べないので、Python 側のシグナルに connect する形にする。)
    // window.__feed_count / __last_feed_bytes は **テスト / デバッグ用** の
    // インスペクション窓口 (test_xterm_terminal_view.py が runJavaScript で参照)。
    // 機密情報を含まないので残置するが、プロダクション用途では参照不要。
    window.__feed_count = 0;
    window.__last_feed_bytes = 0;
    if (bridge.output_b64) {
      bridge.output_b64.connect((b64) => {
        const bytes = base64ToBytes(b64);
        window.__feed_count += 1;
        window.__last_feed_bytes = bytes.length;
        term.write(bytes);
      });
    }

    if (bridge.terminal_cleared) {
      bridge.terminal_cleared.connect(() => {
        term.clear();
      });
    }

    // リサイズ通知
    function reportSize() {
      safeFit();
      bridge.report_resize(term.cols, term.rows);
    }

    new ResizeObserver(() => {
      reportSize();
    }).observe(container);

    term.onResize((evt) => {
      bridge.report_resize(evt.cols, evt.rows);
    });

    // 初期化完了通知
    reportSize();
    bridge.notify_ready();
  }

  // QWebChannel は QtWebEngine が qrc:/// で提供する。
  new QWebChannel(qt.webChannelTransport, function (channel) {
    const bridge = channel.objects.py_bridge;
    if (!bridge) {
      console.error("py_bridge object not found on QWebChannel");
      return;
    }
    attachBridge(bridge);
  });
})();
