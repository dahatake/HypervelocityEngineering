{root_ref}

{app_arch_scope_section}
## 目的
画面一覧に基づき、各画面の詳細定義書を作成する。

## 入力
- `docs/catalog/screen-catalog-APP-*.md`（per-APP 分割された画面カタログ。Arch-UI-List Step 1 の per-APP fan-out 出力。全 APP 分を集約読みする）
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `docs/catalog/persona-screen-catalog.md`（**存在すれば必読**。AAS Step.9 で生成されたペルソナ別共通画面カタログ。`screen-catalog-APP-*.md` の `notes` 列に `common_ref: PSC-XXX` が記載されている画面は本カタログから共通骨格を継承する）

## 出力
- `docs/screen/<画面-ID>-<画面名>-description.md`（画面ごとに1ファイル）

{existing_artifact_policy}

## Custom Agent
`Arch-UI-Detail` を使用

## 依存
- {dep}

## アプリケーション粒度
📋 各画面定義書の「§1 概要」に所属 APP-ID（1:1）を記載すること。`docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照。

## 共通画面（AAS persona-screen-catalog）参照ルール
画面カタログ（`screen-catalog-APP-*.md`）の `notes` 列に `common_ref: PSC-XXX` が記載されている画面については、`docs/catalog/persona-screen-catalog.md` の該当 `persona_screen_id` から **共通骨格**（UX/操作意味/A11y 観点・主要状態）を継承し、画面定義書の「§1 目的と非目的」の冒頭に `共通画面参照: PSC-XXX` を明記する。APP 固有差分（タイトル・項目・遷移先の APP 固有部分）のみを各章に展開する。
分岐ルール:
- `notes` 列に `common_ref: PSC-XXX` が記載されていない画面 → 従来通り単独で画面定義を作成する
- `notes` 列に `common_ref: PSC-XXX` が記載されており、かつ `persona-screen-catalog.md` に当該 `persona_screen_id` が存在する → 共通骨格を継承する
- `notes` 列に `common_ref: PSC-XXX` が記載されているが、`persona-screen-catalog.md` が存在しない、または当該 `persona_screen_id` が見つからない → 共通骨格を捏造せず、画面定義書に `共通画面参照: PSC-XXX（未解決）` と記載し、`{WORK}screen-detail-work-status.md` の `## Issues / Questions` に未解決として記録する

## 完了条件
- 画面定義書が画面一覧に基づいて全て作成されている
{completion_instruction}{additional_section}
