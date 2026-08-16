# 料金 / リアルタイム統計表示ガイド

hve は GitHub Copilot CLI 実行中の **コンテキスト使用量・経過時間・SDK が返す AIU / Premium Requests 相当値・pricing 計算値** を GUI / CUI 両方で ~1Hz で可視化します。本ガイドでは設定・利用方法・トラブルシュートをまとめます。

> **重要 (捏造禁止)**: 料金表が未取得 / 不明モデルの場合、コストは **`-`** と表示されます。推定値で埋めることはしません。

> **公式料金体系との境界 (2026-08-07 照合)**: GitHub 公式ドキュメントでは 2026-06-01 以降、通常の Copilot 課金は **GitHub AI Credits** による使用量課金です。`hve/pricing/` の現行実装は `docs.github.com` の model multiplier と `github.com/pricing` のプラン情報をクロールする **legacy premium request ベースの補助計算**であり、公式の新しい AI Credits 請求額そのものではありません。公式請求額は GitHub の Billing / Usage 画面を正としてください。

> **未配線の範囲 (2026-08-07 実装照合)**: 以下は **モジュールは存在するが利用画面に配線されていない** 範囲です。
>
> - **§4.2 GUI 設定タブ** — [hve/gui/settings_pricing_tab.py](../hve/gui/settings_pricing_tab.py) は存在しますが、[hve/gui/settings_window.py](../hve/gui/settings_window.py) のカテゴリツリー / skill section 登録に含まれておらず、設定画面にタブが追加されません。
>
> GUI Footer / 統計ポップアップ・`hve pricing` CLI・環境変数による pricing 計算・Workbench なし TTY 実行時の CUI StatusLine は配線済みです。

---

## 1. 概要

| 表示項目 | GUI Footer | GUI 統計ポップアップ | CUI StatusLine |
|---|---|---|---|
| Context Window 使用率 | ✅ | ✅ | ✅ |
| Workflow / Step 経過時間 | ✅ | ✅ | ✅ |
| SDK AIU / Premium Requests 相当値 | ✅ | ✅ | ✅ |
| pricing 計算の累積コスト (USD / JPY) | ✅ | ✅ | ✅ |
| 計算方式 / 料金表メタ | – | ✅ | – |

更新間隔: GUI / CUI とも **1 Hz** (1 秒に 1 回)。

---

## 2. 料金データ

### 2.1 取得元と公式料金体系の違い

- **現行実装の取得元**:
  - **モデル multiplier**: [hve/pricing/crawler.py](../hve/pricing/crawler.py) の `DOCS_URL`（GitHub Docs）
  - **プラン定義**: [hve/pricing/crawler.py](../hve/pricing/crawler.py) の `PRICING_URL`（`https://github.com/pricing`）
- **公式の現行課金**:
  - 通常の Copilot プランは GitHub AI Credits を使う使用量課金です（1 AI credit = $0.01 USD）。
  - legacy の model multiplier は、2026-06-01 以降も既存の年額 Copilot Pro / Pro+ で request-based billing に残っている利用者向けの概念です。

取得できた内容だけを `~/.hve/pricing/copilot-pricing.json` に JSON でキャッシュします。取得・解析できない値は `None` / `-` のまま扱い、推定で補完しません。

> **要確認**: [hve/pricing/crawler.py](../hve/pricing/crawler.py) の `DOCS_URL` は legacy 移行後の公式ページ構成とずれている可能性があります。`hve pricing refresh` が失敗した場合は、公式の [Models and pricing for GitHub Copilot](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing) または legacy multiplier ページを確認してください。

### 2.2 キャッシュパス

既定: `~/.hve/pricing/copilot-pricing.json`

環境変数で上書き可能:

```powershell
$Env:HVE_PRICING_CACHE_PATH = "C:\path\to\custom\copilot-pricing.json"
```

### 2.3 自動更新ポリシー

- **月初** (取得日時の月が変わったとき) に自動取得
- **手動**: `hve pricing refresh`（※ GUI 設定タブの「🔄 料金表を今すぐ更新」ボタンは **未配線**。本頁冒頭参照）
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
| `HVE_PRICING_STATUSLINE_ENABLED` | `1` | CUI StatusLine 有効化 (`0` で無効)。`hve/config.py` と `hve/orchestrator.py` で参照されます。 |
| `HVE_NO_STATUSLINE` | (未設定) | 設定時は StatusLine を常に抑止。`hve/statusline.py` で参照されます。 |

#### 通貨表示モード

| モード | 例 (USD=$0.40, JPY=¥60) | 用途 |
|---|---|---|
| `auto` | locale=`ja` → `$0.4000 (¥60)`, それ以外 → `$0.4000` | 既定 |
| `both` | `$0.4000 (¥60)` | 日本向け |
| `usd` | `$0.4000` | グローバル / Copilot 請求基準 |
| `jpy` | `¥60` | 簡易見積もり |

### 4.2 GUI 設定タブ（**未配線**）

> [hve/gui/settings_pricing_tab.py](../hve/gui/settings_pricing_tab.py) にウィジェット実装は存在しますが、[hve/gui/settings_window.py](../hve/gui/settings_window.py) のカテゴリツリー / skill section 登録に含まれておらず設定画面にタブが出ません。下記は配線時の仕様予定です。現時点では §4.1 の環境変数で設定してください。

`設定` → `料金 / 統計` タブで以下を編集できる想定です:

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

- **スナップショット**: System / User Context / Reasoning & Cache / Latency / Step Activity / Compaction / Permission / **Cost (pricing 計算)** / **Elapsed** / その他 (1Hz 再構築)
  - Cost セクション項目: 累積コスト (pricing 計算) / Premium Requests 累積 / 計算方式 / USD/JPY レート / 料金表 取得日時 / 料金表 ステータス / 未計算理由 (該当時のみ)
  - Elapsed セクション項目: Workflow 経過 / Step 経過
- **今回の実行履歴**: 既存履歴ビュー

---

## 6. CUI StatusLine

[hve/statusline.py](../hve/statusline.py) に `StatusLine` / `format_status_line()` の実装があり、[hve/orchestrator.py](../hve/orchestrator.py) の `_attach_runtime_statusline()` から **Workbench を使わない TTY 実行時** に起動されます。Workbench UI が有効な GUI / TUI 実行では Workbench 側の表示を優先し、StatusLine は起動しません。

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
2. モデル multiplier が料金表に無い → ポップアップ「Cost (pricing 計算)」セクションの **未計算理由** を確認 (`model_not_found` 等)
3. プラン未指定で additional_request_usd が解決できない → 料金表 `status` を確認

**捏造禁止ポリシー**: 不明値を埋めずに `-` 表示するのは仕様です。

### Q2. StatusLine が出ない

§6 のとおり StatusLine は Workbench を使わない TTY 実行時のみ表示されます。表示されない場合は、`quiet` / `final_only`、Workbench 有効、`stderr.isatty() == False`、`HVE_NO_STATUSLINE`、`HVE_PRICING_STATUSLINE_ENABLED=0` のいずれかを確認してください。

### Q3. 料金表取得が失敗する

- ネットワーク到達性を確認
- GitHub Docs / Pricing ページ HTML 構造変更の可能性 → CHANGELOG / Issue を確認
- 部分成功時は `status="partial"` でキャッシュされ、不足部分のみ `-` 表示

### Q4. JPY 換算値が実勢レートと違う

固定レートのため正確性は保証しません。`HVE_PRICING_USD_JPY_RATE` で調整してください（GUI 設定タブは **未配線**。§4.2 参照）。リアルタイム為替 API 連携は将来検討。

---

## 8. 関連ファイル

- `hve/pricing/` — 料金表モデル / クローラ / キャッシュ / 計算
- `hve/gui/text_kinsoku.py` — フォーマット共通ヘルパ (Qt 非依存)
- `hve/gui/workbench_widgets.py` `FooterWidget` — GUI Footer
- `hve/gui/stats_detail_popup.py` — 統計ポップアップ
- `hve/gui/settings_pricing_tab.py` — GUI 設定タブ（**未配線**：settings_window から import されていない）
- `hve/statusline.py` — CUI StatusLine（**配線済み**：[hve/orchestrator.py](../hve/orchestrator.py) の `_attach_runtime_statusline()` から起動）
- `hve/tests/pricing/` — 全 67 件のテスト

---

## 9. 変更履歴

機能リリース履歴は [`CHANGELOG.md`](../CHANGELOG.md) の "Added — リアルタイム統計 + AI Credit 料金表示" を参照。ただし CHANGELOG には過去時点の「StatusLine 未統合」記録も残るため、現状は本頁の実装照合結果を優先してください。

## 10. 公式出典

- Usage-based billing for individuals — <https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals>
- Usage-based billing for organizations and enterprises — <https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-organizations-and-enterprises>
- Model multipliers for annual plans on request-based billing (legacy) — <https://docs.github.com/en/copilot/reference/copilot-billing/request-based-billing-legacy/model-multipliers-for-annual-plans>
- GitHub Copilot is moving to usage-based billing — <https://github.blog/news-insights/company-news/github-copilot-is-moving-to-usage-based-billing/>
- Pricing · Plans for every developer · GitHub — <https://github.com/pricing>
