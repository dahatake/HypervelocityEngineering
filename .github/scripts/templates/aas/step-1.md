{root_ref}
## 目的
ユースケース文書を根拠に、実装手段を仕分けし、アプリケーションリストを作成する。

## 入力
- `docs/catalog/use-case-catalog.md`

## 出力
- `docs/catalog/app-catalog.md`

## Custom Agent
`Arch-ApplicationAnalytics`

## 依存
- なし（最初に実行）

## 完了条件
- `docs/catalog/app-catalog.md` が作成されている
- 完了時に自身に `aas:done` ラベルを付与すること{additional_section}
