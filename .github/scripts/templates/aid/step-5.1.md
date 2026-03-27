{root_ref}
## 目的
画面一覧に基づき、各画面の詳細定義書を作成する。

## 入力
- `docs/screen-list.md`

## 出力
- `docs/screen/<画面-ID>-<画面名>-description.md`（画面ごとに1ファイル）

## Custom Agent
`Arch-UI-Detail` を使用

## 依存
- {dep}

## 完了条件
- 画面定義書が画面一覧に基づいて全て作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
