{root_ref}

{app_arch_scope_section}
## 目的
ドメイン分析結果、サービス一覧、データモデルを根拠に画面一覧を設計する。

## 入力
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）
- `docs/catalog/persona-screen-catalog.md`（存在する場合のみ。AAS Step.9 で生成される共通画面骨格）

## 出力
- `docs/catalog/screen-catalog-{APP-ID}.md`（**APP-ID 単位で分割**。担当 APP の画面のみを書く）

{existing_artifact_policy}

## Custom Agent
`Arch-UI-List` を使用

## 依存
- 先行ステップなし（`aad-web` の起点ステップ）

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、各画面に「所属APP」（1:1）を記載すること。
本 Step は per-APP fan-out で並列起動される。各 fan-out 子は担当 APP の `screen-catalog-{APP-ID}.md` のみを出力する。

## 共通画面（AAS persona-screen-catalog）との関係
`docs/catalog/persona-screen-catalog.md` が存在する場合は参照し、当該カタログに記載された共通画面骨格を本 APP 用に再定義しない。担当 APP の画面カタログには、共通画面については `notes` 列に `common_ref: PSC-XXX`（`persona-screen-catalog.md` で採番された `persona_screen_id`）を記載し、APP 固有差分がある場合のみ短く追記する。共通画面骨格自体を再生成・上書きしてはならない。詳細な画面定義は AAD-WEB Step.2.1（Arch-UI-Detail）で行う。
`persona-screen-catalog.md` が存在しない場合は従来通り独自に画面一覧を生成する。

## 完了条件
- `docs/catalog/screen-catalog-{担当 APP-ID}.md` が作成されている
{completion_instruction}{additional_section}
