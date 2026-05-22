{root_ref}

> **⚠️ 任意ステップ**
> 本 Step は ARD パラメータ `include_kpi_okr=true` の場合のみ実行されます（既定 `false`）。CLI `--include-kpi-okr` / `--steps 3` / Step 1 ワークフロー選択画面のグループチェック / 対話ウィザードのいずれかで明示的に有効化してください。

## 目的
ARD ワークフロー Step 3（任意）。事業要件文書の **戦略的記述**（To-Be ビジョン / 戦略的方向性 / 戦略的アクションプラン / 主要 KPI に相当する記述）を根拠に、KPI/OKR、計測データ定義、目的志向のデータ収集設計を作成し、`docs/recommended-kpi-okr.md` を生成する。

## 入力
- 一次情報（いずれか優先順）:
  - `docs/business-requirement.md`（Step 2 出力。存在時優先）
  - `docs/company-business-requirement.md`（Step 1.2 出力。フォールバック）
- 参考（任意）: `original-docs/*`, `docs/business/*-analysis.md`
- 対象企業名: `{company_name}`（任意）
- 分析対象事業・業務名: `{target_business}`（任意）
- 調査期間年数: `{survey_period_years}` 年
- 対象地域: `{target_region}`
- 分析目的: `{analysis_purpose}`

## 出力
- `docs/recommended-kpi-okr.md`（推奨 KPI/OKR 定義書）

## Custom Agent
`Arch-ARD-KPIOKRDefinition`

## 依存
- Step 2（`docs/business-requirement.md`）。Step 2 がスキップ経路の場合は Step 1.2（`docs/company-business-requirement.md`）をソースとして使用する。

## 後続工程での参照
- ARD Step 4.1（ユースケース骨格）/ Step 4.2（ユースケース詳細）が **任意参照**
- `aas`（アプリケーション選定）の `Arch-ApplicationAnalytics` Agent が **任意参照** し、`docs/catalog/app-catalog.md` の「対応 KPI/OKR」列に APP-ID と KPI/OKR ID を紐付ける
- テスト仕様（`docs/test-specs/`）への KPI/OKR ID 紐付け運用ルールを成果物 §7.2 で提示

## 完了条件
- `docs/recommended-kpi-okr.md` が作成されている
- 必須セクション 1〜7（Executive Summary / 戦略目標マッピング / KPI 定義 / OKR 定義 / 計測データ定義 / データ収集設計 / ID 命名規約と引き継ぎ）が含まれる
- 各 ID が命名規約（`ST-*`, `KPI-*`, `OKR-*`, `KR-*-*`, `DAT-*`）に準拠
- すべての KPI/OKR 項目に信頼度区分（資料上確認できる事実 / 外部情報補足 / 合理的仮説 / 追加確認必要論点）が付与されている
- 「6. データ収集設計」に各 KPI/OKR ID のイベント名・属性スキーマ・計測実装手段（Application Insights / OpenTelemetry 等）が記載されている
- 一次情報に記載のない目標値は「合理的仮説」「追加確認必要論点」のいずれかに分類されている
{completion_instruction}{additional_section}
