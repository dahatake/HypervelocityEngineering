"""hve.gui.markdown_preview.download_assets — Mermaid / KaTeX アセットダウンロード。

setup スクリプト (setup-hve.cmd / .ps1 / .sh) から呼び出される。クリーン環境で
GUI Orchestrator の Markdown プレビューを動作させるために、Mermaid と KaTeX の
JS / CSS アセットを jsdelivr CDN から取得して
``hve/gui/markdown_preview/assets/`` 配下に配置する。

設計:
    - 標準ライブラリ ``urllib`` のみ使用（追加依存なし）。
    - 既にファイルが存在する場合はスキップ（再実行で再ダウンロードしない）。
    - ネットワーク失敗時は警告のみで終了コード 0（setup を中断しない）。
    - 取得バージョンは下記定数で固定（再現性確保）。

実行方法:
    python -m hve.gui.markdown_preview.download_assets

オプション:
    --force    既存ファイルがあっても再取得する
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


# 固定バージョン（変更時は LICENSE-third-party.md も更新すること）
MERMAID_VERSION = "10.9.0"
KATEX_VERSION = "0.16.9"


def _assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def _targets() -> List[Tuple[str, str]]:
    """[(URL, ローカルファイル名), ...] のリストを返す。"""
    return [
        (
            f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js",
            "mermaid.min.js",
        ),
        (
            f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.js",
            "katex.min.js",
        ),
        (
            f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css",
            "katex.min.css",
        ),
        (
            f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/contrib/auto-render.min.js",
            "katex-auto-render.min.js",
        ),
    ]


def _download_one(url: str, dest: Path, *, timeout: float = 30.0) -> bool:
    """1 ファイルをダウンロードする。成功 True / 失敗 False。

    HTML エラーページが 200 で返るケースを排除するため、最低サイズ 1 KB
    を満たさないペイロードは失敗扱いとする。
    """
    try:
        req = Request(url, headers={"User-Agent": "hve-setup/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (URLError, HTTPError, TimeoutError) as exc:
        print(f"  [WARN] {url}\n         ダウンロード失敗: {exc}", file=sys.stderr)
        return False
    except Exception as exc:  # pragma: no cover
        print(f"  [WARN] {url}\n         予期せぬエラー: {exc}", file=sys.stderr)
        return False

    if len(data) < 1024:
        # HTML エラーページや空応答を弾く
        print(
            f"  [WARN] {url}\n         サイズが小さすぎます ({len(data)} bytes) — エラーページ応答の可能性",
            file=sys.stderr,
        )
        return False

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError as exc:
        print(f"  [WARN] 書き込み失敗: {dest} ({exc})", file=sys.stderr)
        return False

    print(f"  OK  {dest.name}  ({len(data):,} bytes)")
    return True


def main(force: bool = False) -> int:
    assets = _assets_dir()
    assets.mkdir(parents=True, exist_ok=True)

    print(f"[hve] Markdown プレビュー用アセット取得 ({assets})")
    print(f"[hve] Mermaid {MERMAID_VERSION} / KaTeX {KATEX_VERSION}")

    total = 0
    succeeded = 0
    skipped = 0
    for url, name in _targets():
        total += 1
        dest = assets / name
        if dest.exists() and not force:
            print(f"  SKIP {name}  (既存、--force で再取得)")
            skipped += 1
            continue
        if _download_one(url, dest):
            succeeded += 1

    failed = total - succeeded - skipped
    print(
        f"[hve] アセット取得結果: 成功 {succeeded} / スキップ {skipped} / 失敗 {failed} / 合計 {total}"
    )
    if failed > 0:
        print(
            "[hve] 一部失敗しました。ネットワーク到達性を確認するか、手動で配置してください。\n"
            "       手順: hve/gui/markdown_preview/assets/LICENSE-third-party.md",
            file=sys.stderr,
        )
        # setup を止めないが、setup スクリプト側で WARN カウントするため非ゼロを返す。
        return 2
    return 0


if __name__ == "__main__":
    force = "--force" in sys.argv[1:]
    sys.exit(main(force=force))
