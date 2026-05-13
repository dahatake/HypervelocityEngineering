{root_ref}

{app_arch_scope_section}
## 目的
TDD GREEN フェーズ: テスト仕様書 (`docs/test-specs/`) を参照しながらテストファーストで実装する。
画面定義書に基づき、対象画面のUIを実装し、サービスカタログに基づくAPIクライアント層を整備する（APP-ID 指定時はスコープ内の画面のみ）。

## 入力
- `docs/screen/{画面ID}.md`（画面ID 例: `SCR-XXX-YYY`）
- `docs/catalog/screen-catalog.md`
- `docs/catalog/service-catalog-matrix.md`
- UI実装技術: `HTML5/CSS/JavaScript（リポジトリ既存規約に合わせる）`
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `src/data/sample-data.json`
- TDD テストコード（RED状態）: `test/ui/`（Step.3.0TC の成果物）
- テスト仕様書: `docs/test-specs/{screenId}-test-spec.md`（Step.3.0T で生成済み。TDD RED フェーズのテストケース定義）

## 出力
- `src/app/` 配下にUI実装

{existing_artifact_policy}

## TDD GREEN フロー（反復）
1. Jest テストで全テスト FAIL（RED 状態）を確認する
2. テストケースを GREEN にするための最小 UI 実装を作成する
3. Jest テストを実行する
4. 全テスト PASS なら REFACTOR へ進む。FAIL があれば実装を修正して手順3に戻る
5. 最大 {tdd_max_retries} 回反復する
6. {tdd_max_retries} 回で全 PASS にならない場合: `asdw-web:blocked` ラベルを付与し、未 PASS テスト一覧を Issue コメントで報告する

## テストコード保護ルール
- GREEN フェーズでは UI 実装コードのみを修正する（`test/ui/` のテストコードは原則変更禁止）

## Custom Agent
`Dev-Microservice-Azure-UICoding` を使用

## 依存
- Step.3.0TC（UI テストコード生成）が `asdw-web:done` であること

## 完了条件
- `src/app/` 配下にUI実装が完成している
{completion_instruction}{app_id_section}{additional_section}
