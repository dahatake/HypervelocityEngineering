<!-- DEPRECATED: このテンプレートは templates/aad-web/step-2.1.md に移動しました。 -->
{root_ref}
## 目的
画面一覧に基づき、各画面の詳細定義書を作成する。

## 入力
- `docs/catalog/screen-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/screen/<画面-ID>-<画面名>-description.md`（画面ごとに1ファイル）

## Custom Agent
`Arch-UI-Detail` を使用

## 依存
- {dep}

## アプリケーション粒度
📋 各画面定義書の「§1 概要」に所属 APP-ID（1:1）を記載すること。`docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照。

## 完了条件
- 画面定義書が画面一覧に基づいて全て作成されている
{completion_instruction}{additional_section}
