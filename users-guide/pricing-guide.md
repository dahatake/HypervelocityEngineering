# 料金 / リアルタイム統計表示ガイド

hve は GitHub Copilot CLI 実行中の **コンテキスト使用量・経過時間・AI Credit 料金 (Premium Requests)** を GUI / CUI 両方で ~1Hz で可視化します。本ガイドでは設定・利用方法・トラブルシュートをまとめます。

> **重要 (捏造禁止)**: 料金表が未取得 / 不明モデルの場合、コストは **`-`** と表示されます。推定値で埋めることはしません。

---

## 1. 概要

| 表示項目 | GUI Footer | GUI 統計ポップアップ | CUI StatusLine |
|---|---|---|---|
| Context Window 使用率 | ✅ | ✅ | ✅ |
| Workflow / Step 経過時間 | ✅ | ✅ | ✅ |
| 累積コスト (USD / JPY) | ✅ | ✅ | ✅ |
| Premium Requests 累積 | ✅ | ✅ | ✅ |
| 計算方式 / 料金表メタ | – | ✅ | – |

更新間隔: GUI / CUI とも **1 Hz** (1 秒に 1 回)。

---

## 2. 料金データ

### 2.1 取得元

- **モデル multiplier** (例: `claude-sonnet-4 = 1.0`): GitHub Docs (docs.github.com)
- **プラン定義** (例: `copilot_pro` の月額・追加 Premium Request 単価): github.com/pricing

両者を **公式情報のみ** から取得し、`~/.hve/pricing/copilot-pricing.json` に JSON でキャッシュします。

### 2.2 キャッシュパス

既定: `~/.hve/pricing/copilot-pricing.json`

環境変数で上書き可能:

```powershell
$Env:HVE_PRICING_CACHE_PATH = "C:\path\to\custom\copilot-pricing.json"
```

### 2.3 自動更新ポリシー

- **月初** (取得日時の月が変わったとき) に自動取得
- **手動**: `hve pricing refresh` または GUI 設定タブの「🔄 料金表を今すぐ更新」
- **失敗時**: 両ソース失敗 → エラー。片方のみ成功 → `status="partial"` で記録 (利用可)

---

## 3. CLI コマンド

### 3.1 料金表の表示

```powershell
hve pricing show
```

現在キャッシュされている料金表 (モデル multiplier・プラン定義・取得日時・status) を表示します。

### 3.2 料金表の強制更新

```powershell
hve pricing refresh
```

GitHub Docs / Pricing ページから最新を取得しキャッシュを上書きします。

---

## 4. 設定

### 4.1 環境変数

| 環境変数 | 既定値 | 説明 |
|---|---|---|
| `HVE_PRICING_USD_JPY_RATE` | `150.0` | USD → JPY 換算固定レート |
| `HVE_PRICING_CURRENCY` | `auto` | 表示通貨。`auto` / `usd` / `jpy` / `both` |
| `HVE_PRICING_AUTO_REFRESH` | `1` | 月初自動取得 (`0` で無効) |
| `HVE_PRICING_CACHE_PATH` | `~/.hve/pricing/copilot-pricing.json` | キャッシュファイルパス |
| `HVE_PRICING_STATUSLINE_ENABLED` | `1` | CUI StatusLine 有効化 (`0` で無効) |
| `HVE_NO_STATUSLINE` | (未設定) | 設定時は StatusLine を常に抑止 |

#### 通貨表示モード

| モード | 例 (USD=$0.40, JPY=¥60) | 用途 |
|---|---|---|
| `auto` | locale=`ja` → `$0.4000 (¥60)`, それ以外 → `$0.4000` | 既定 |
| `both` | `$0.4000 (¥60)` | 日本向け |
| `usd` | `$0.4000` | グローバル / Copilot 請求基準 |
| `jpy` | `¥60` | 簡易見積もり |

### 4.2 GUI 設定タブ

`設定` → `料金 / 統計` タブで以下を編集できます (Wave 4 で追加):

- USD/JPY レート
- 通貨表示モード
- 月初自動取得 On/Off
- CUI ステータスライン On/Off
- 料金表キャッシュの最終取得日時 / モデル件数 / プラン件数表示
- 「🔄 料金表を今すぐ更新」ボタン

---

## 5. GUI 表示

### 5.1 Footer (1Hz)

ウィンドウ最下部に常時 1 行で表示されます:

```
Context: 12,345 / 200,000 (6%) | Model: claude-sonnet-4 | Elapsed: 00:01:23
 | Step prep: 00:00:42 | Cost: $0.4000 (¥60) | Reqs: 10
 | Tools (Step): read_file×3 | Skills (Step): -
```

- 折り返し可 (`wordWrap=True`)、`|` 区切りには ZWSP (U+200B) を挿入し折り返ししやすく、項目 "label: value" 内は `&nbsp;` で改行禁止。
- 日本語行頭禁則 (`。、）] 」` 等) が行頭に来ないよう簡易調整。

### 5.2 統計ポップアップ

Footer の **「📊 統計情報」** ボタンで表示。タブ:

- **スナップショット**: System / User Context / Reasoning & Cache / Latency / Step Activity / Compaction / Permission / **Cost (AI Credit)** / **Elapsed** / その他 (1Hz 再構築)
  - Cost セクション項目: 累積コスト / Premium Requests 累積 / 計算方式 / USD/JPY レート / 料金表 取得日時 / 料金表 ステータス / 未計算理由 (該当時のみ)
  - Elapsed セクション項目: Workflow 経過 / Step 経過
- **今回の実行履歴**: 既存履歴ビュー

---

## 6. CUI StatusLine

### 6.1 表示例

```
[hve] WF 00:01:23 | Step prep 00:00:42 | Sub impl 00:00:11 | ctx 12,345/200,000 (6%) | cost $0.4000 (¥60) | reqs 10
```

- 1Hz で `\r\x1b[2K` を使い同一行を上書き
- 停止時は最終 clear を出して改行
- 出力先: 既定 `stderr` (通常の `stdout` ログを汚さない)

### 6.2 自動抑止条件

以下のいずれかで StatusLine は **無効化** されます:

1. `stderr.isatty() == False` (リダイレクト / パイプ / CI ログ)
2. `HVE_NO_STATUSLINE` 環境変数がセットされている
3. アプリ側で `enabled=False` 指定

### 6.3 プログラムから利用

```python
from hve.statusline import StatusLine, StatusLineState
import time

with StatusLine(interval=1.0) as sl:
    sl.update_state(StatusLineState(
        workflow_started_at=time.monotonic(),
        context_current=12345,
        context_limit=200000,
        cost_usd_total=0.4,
        cost_jpy_total=60.0,
        premium_requests_total=10,
    ))
    # ... 任意の処理 ...
```

---

## 7. トラブルシュート

### Q1. Cost が `-` のまま表示されない

主な原因:

1. 料金表未取得 → `hve pricing refresh` を実行
2. モデル multiplier が料金表に無い → ポップアップ「Cost (AI Credit)」セクションの **未計算理由** を確認 (`model_not_found` 等)
3. プラン未指定で additional_request_usd が解決できない → 料金表 `status` を確認

**捏造禁止ポリシー**: 不明値を埋めずに `-` 表示するのは仕様です。

### Q2. StatusLine が出ない

1. ターミナルが TTY か確認 (`python -c "import sys; print(sys.stderr.isatty())"`)
2. `HVE_NO_STATUSLINE` が未設定か確認
3. `HVE_PRICING_STATUSLINE_ENABLED=1` か確認

### Q3. 料金表取得が失敗する

- ネットワーク到達性を確認
- GitHub Docs / Pricing ページ HTML 構造変更の可能性 → CHANGELOG / Issue を確認
- 部分成功時は `status="partial"` でキャッシュされ、不足部分のみ `-` 表示

### Q4. JPY 換算値が実勢レートと違う

固定レートのため正確性は保証しません。`HVE_PRICING_USD_JPY_RATE` または GUI 設定タブで調整してください。リアルタイム為替 API 連携は将来検討。

---

## 8. 関連ファイル

- `hve/pricing/` — 料金表モデル / クローラ / キャッシュ / 計算
- `hve/gui/text_kinsoku.py` — フォーマット共通ヘルパ (Qt 非依存)
- `hve/gui/workbench_widgets.py` `FooterWidget` — GUI Footer
- `hve/gui/stats_detail_popup.py` — 統計ポップアップ
- `hve/gui/settings_pricing_tab.py` — GUI 設定タブ
- `hve/statusline.py` — CUI StatusLine
- `hve/tests/pricing/` — 全 67 件のテスト

---

## 9. 変更履歴

機能リリース履歴は [`CHANGELOG.md`](../CHANGELOG.md) の "Added — リアルタイム統計 + AI Credit 料金表示" を参照。
