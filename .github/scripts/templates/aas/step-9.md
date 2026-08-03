{root_ref}
## 目的
ユースケース文書から横断的なペルソナ（アクター・ロール）を抽出し、`docs/catalog/persona-catalog.md` を作成する。
本ステップは APP-ID 横断の単一の真実源（SoT）として、複数 APP-ID に登場する同一ペルソナの重複定義を防ぎ、後続 Step.8（ペルソナ別共通画面カタログ）の前提となる。

## 抽出観点
- ユースケースのアクター記述・主要ペルソナ記述を一次ソースとして、横断ペルソナ一覧を抽出する
- 同一の業務的役割を持つアクターが複数 APP-ID に登場する場合は、1 つのペルソナに統合し「登場APP」（N:N）を記載する
- 各ペルソナに対して `persona_id（PRS-XXX）/ persona_name / category / description / source_actor_names / referenced_ucs / linked_apps` を記載する
- **ペルソナID 採番ルール**: ユースケースに既存アクターID がある場合は流用する。無い場合は `PRS-001` 形式で暫定採番する（PRS = Persona）。ID は Step.8 等からの参照安定化のためで、新規ペルソナ概念を作らない
- **根拠ユースケースID は必須**。各ペルソナ行に最低 1 件の `根拠ユースケースID` を記載し、当該 ID は `use-case-catalog.md` に存在すること
- ユースケースに根拠のないペルソナは正式登録しない（推測禁止）。ただし業務上必要性が示唆されるが根拠不足のものは、本表ではなく別表「要確認候補」として分離して記録する
- 不明な項目は推測せず `TBD` または `不明（要確認）` と明記する（ただし `根拠ユースケースID` への TBD は禁止）

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

## 出力
- `docs/catalog/persona-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-PersonaCatalog` を使用

## 依存
- `docs/catalog/use-case-catalog.md` および `docs/catalog/app-catalog.md` が利用可能であること
- ワークフロー上は Step.7 後に実行する（Step.7 成果物との内容依存はない）

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、各ペルソナに `linked_apps`（N:N）を記載すること。

## 完了条件
- `docs/catalog/persona-catalog.md` が作成されている
- 各ペルソナに `persona_id（PRS-XXX）/ persona_name / category / description / source_actor_names / referenced_ucs / linked_apps` が記載されている
- 全ペルソナ行に 1 件以上の `referenced_ucs` が記載され、当該 ID が `use-case-catalog.md` に存在すること
- 根拠不足の人物像は本表ではなく「要確認候補」表に分離されている（または該当なし）
{completion_instruction}{additional_section}
