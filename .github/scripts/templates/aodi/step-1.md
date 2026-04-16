{root_ref}
## 目的
`original-docs/` フォルダーの原本ドキュメントを D01〜D21 に分類し、`knowledge/business-requirement-document-status.md` と `knowledge/D{NN}-<文書名>.md` を生成・更新する。矛盾検出と SoT 優先順位に基づく未解決記録も実施する。

## Custom Agent
`QA-OriginalDocsImporter`

## 処理フロー
QA-OriginalDocsImporter Agent の定義に従い、以下の処理を 1 セッション内で順次実行する。

1. **入力ファイル収集** — スコープに従い `original-docs/*` を収集する
2. **マスターリスト読み込み** — `template/business-requirement-document-master-list.md` を読み込む
3. **セクション抽出・正規化** — 見出し単位でセクションを分割し、セクション ID を生成する
4. **D01〜D21 マッピング** — Primary D / Contributing D を判定する（knowledge-management-guide §9）
5. **状態判定** — Confirmed / Tentative / Unknown / Conflict を判定する
6. **矛盾検出** — 同一D・D間・qa/ との矛盾・用語矛盾を検出する（knowledge-management-guide §10）
7. **status.md 生成** — `knowledge/business-requirement-document-status.md` を §4 テンプレートに従い生成・更新する
7.5. **knowledge/ 文書生成** — マッピングが存在する各 D クラスについて `knowledge/D{NN}-<文書名>.md` を §7 テンプレートに従い個別生成する（マッピング 0 件はスキップ）
8. **敵対的レビュー**（オプション）— 指定時のみ adversarial-review を実行する

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| スコープ | `{aodi_scope}` |
| force_refresh | `{aodi_force_refresh}` |
{aodi_target_files_section}

## 入力
- `original-docs/*`（スコープに応じてフィルタリング）
- `template/business-requirement-document-master-list.md`
- `.github/skills/planning/knowledge-management/references/knowledge-management-guide.md`

## 出力
- `knowledge/business-requirement-document-status.md`（生成・更新）
- `knowledge/D{NN}-<文書名>.md`（マッピングが存在する D クラス数だけ個別生成）

## 依存
- なし（最初に実行）

## 完了条件
- `knowledge/business-requirement-document-status.md` が生成・更新されている
- マッピングが存在する各 D クラスについて `knowledge/D{NN}-<文書名>.md` が生成されている
- 矛盾一覧と横断未決一覧が status.md に反映されている
- 完了時に自身に `aodi:done` ラベルを付与すること{additional_section}
