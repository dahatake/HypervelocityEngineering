{root_ref}
## 目的
画面一覧に基づき、各画面の詳細定義書を作成する。

## 入力
- `docs/screen-list.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/screen/<画面-ID>-<画面名>-description.md`（画面ごとに1ファイル）

## Custom Agent
`Arch-UI-Detail` を使用

## 依存
- {dep}

## アプリケーション粒度
📋 各画面定義書の「§1 概要」に所属 APP-ID（1:1）を記載すること。`docs/app-list.md` の「アプリ一覧（アーキタイプ）概要」を参照。

## 完了条件
- 画面定義書が画面一覧に基づいて全て作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
