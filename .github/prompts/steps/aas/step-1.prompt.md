{root_ref}
## 目的
アプリケーションリストの各APPについて、必須のAPP別要求定義書を根拠に固定候補からアーキテクチャを選定する。

## 入力
- `docs/catalog/app-catalog.md`
- `docs/architectural-requirements-app-NNN.md`（対象APPごとに必須）
- `knowledge/D01`, `D02`, `D05`, `D09`, `D15`, `D19`（任意補強。非機能要件・業務制約の裏付けに使う）

## 出力
- `docs/catalog/app-arch-catalog.md`

{existing_artifact_policy}

## 注意
- 要求定義書の欠落、schema不正、APP-ID不一致、または `TBD` かつ `Blocker=yes` があれば対象APPを fail-closed で停止する
- 必須入力を他の属性や固定候補から補完しない
- 詳細要求は `markdown-query` で対象Requirement IDだけを選択取得する

## Custom Agent
`Arch-ArchitectureCandidateAnalyzer`

## 依存
- AAS Workflow内の依存Stepはなし（単一root Step）
- Workflow間の前提成果物: ARD Step 4.1の`app-catalog.md`とARD Step 4.2のAPP別要求定義書

## 完了条件
- `docs/catalog/app-arch-catalog.md` が作成されている
{completion_instruction}{additional_section}
