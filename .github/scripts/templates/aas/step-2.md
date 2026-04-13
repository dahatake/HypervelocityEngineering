{root_ref}
## 目的
アプリケーションリスト（docs/catalog/app-catalog.md）の各APPに対し、個別の入力ファイル（docs/architectural-requirements-app-xx.md）から非機能要件を読み取り、固定の候補リストからアーキテクチャを選定する。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/architectural-requirements-app-xx.md`（存在するもののみ）

## 出力
- `docs/catalog/app-arch-catalog.md`

## 注意
- 全APPの入力ファイルが揃っていなくても実行可能です
- 存在する入力ファイルのみ処理され、存在しないAPPは「未処理」として記録されます
- ユーザーが `docs/architectural-requirements-app-xx.md` を作成する手順は users-guide/02-app-architecture-design.md の Step 2 を参照してください

## Custom Agent
`Arch-ArchitectureCandidateAnalyzer`

## 依存
- Step.1（アプリケーションリストの作成）が `aas:done` であること

## 完了条件
- `docs/catalog/app-arch-catalog.md` が作成されている
- 完了時に自身に `aas:done` ラベルを付与すること{additional_section}
