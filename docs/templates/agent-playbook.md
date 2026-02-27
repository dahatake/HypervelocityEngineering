# Agent Playbook（常駐情報）

## 目的
- 指示ファイル（copilot-instructions / AGENTS / instructions）を短く保つための参照資料。

## 定義
- 「10分」：エージェントの作業時間見積り（壁時計ベースのラフな X–Y 分レンジ）。
- 「Shard」：パススコープの指示（`.github/instructions/*.instructions.md` の applyTo と、ネスト AGENTS.md）。

## リポジトリ構成（概要）
- lib/: 主要ライブラリパッケージ
- admin/: 管理者向けUI
- config/: 設定ファイル/テンプレ
- docs/: ドキュメント
- data/: アプリで使うデータ
- test/: テスト用ヘルパー/フィクスチャ
- src/: ビルド前ソース
- app/: ビルド後成果物
- api/: APIコード
- infra/: インフラコード
- work/: 計画/進捗/分割Prompt

## 日本向け運用（圧縮版）
- UI文言/ドキュメントは日本語優先。
- 個人情報・ログ・規制領域は日本の法規制/コンプラ影響があり得るため、前提と確認事項を明示（断定しない）。

## 分割（Split Mode）用 Prompt テンプレ
## Parent Issue
- <link or placeholder>

## Goal
- ...

## Plan
- [ ] ... (X–Y min)

## Dependencies
- Inputs:
- Outputs（paths）:

## Parallelism
- ...

## Risks & Checks
- ...

## Questions
- ...（最大3、無ければNone）
