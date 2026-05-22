# Markdown Preview 同梱第三者ライセンス

本ディレクトリには `hve` GUI Orchestrator の Markdown プレビュー機能で使用する
第三者製 JavaScript / CSS アセットを配置します。各アセットのライセンス遵守のため、
著作権表示と参照元 URL を以下に列挙します。

## アセット一覧

`hve/setup-hve.cmd` / `setup-hve.ps1` / `setup-hve.sh` のいずれかを実行すると、
以下のバージョンが jsdelivr CDN から自動ダウンロードされます。

### Mermaid

- ファイル: `mermaid.min.js`
- ライセンス: MIT License
- 入手元 URL: `https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js`
- リポジトリ: https://github.com/mermaid-js/mermaid
- 取得バージョン: `10.9.0`

### KaTeX

- ファイル: `katex.min.js`, `katex.min.css`, `katex-auto-render.min.js`
- ライセンス: MIT License
- 入手元 URL:
  - `https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js`
  - `https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css`
  - `https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js`（→ `katex-auto-render.min.js` にリネーム）
- リポジトリ: https://github.com/KaTeX/KaTeX
- 取得バージョン: `0.16.9`

## Python 依存ライブラリのライセンス

本機能は以下の Python ライブラリにも依存します（`pip install -e ".[gui]"` で導入、本ディレクトリには含まれません）。

- **markdown-it-py** (MIT License) — https://github.com/executablebooks/markdown-it-py
- **mdit-py-plugins** (MIT License) — https://github.com/executablebooks/mdit-py-plugins
- **Pygments** (BSD 2-Clause License) — https://pygments.org/

## 取得・更新手順

### 自動（推奨）

```
python -m hve.gui.markdown_preview.download_assets
```

`setup-hve.*` から自動的に呼ばれます。既存ファイルがあればスキップします。
強制再取得する場合は `--force` を付けます。

### 手動

ネットワーク制限環境では、上記 URL から手動でダウンロードして
本ディレクトリ（`hve/gui/markdown_preview/assets/`）に配置してください。
未配置でも通常の Markdown 本文はレンダリングされます（Mermaid 図と数式のみ無効化）。

### バージョン更新

`hve/gui/markdown_preview/download_assets.py` の `MERMAID_VERSION` / `KATEX_VERSION`
定数を更新後、本ファイルの「取得バージョン」も併せて更新してください。
