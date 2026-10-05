{root_ref}
## 目的
`qa/` または `docs-original/`（または両方）から D01〜D21 へのマッピングを実施し、`knowledge/business-requirement-document-status.md` と `knowledge/D{NN}-<文書名>.md` を生成・更新する。

## Custom Agent
`KnowledgeManager`

## 処理フロー
1. **Step 0: ソース判定・取り込み手法自動選択**（パス判定優先、内容判定フォールバック）
2. **Step 0.5: STALENESS CHECK**（`sources` に `original-docs` を含む場合のみ）
3. **Step 1: 入力ファイル収集**
4. **Step 2: マスターリスト読み込み**
5. **Step 3: 質問項目/セクション抽出・正規化**
6. **Step 4: D01〜D21 マッピング**
7. **Step 5: 状態判定（Confirmed/Tentative/Unknown/Conflict）**
8. **Step 6: カバレッジ分析**
9. **Step 6.5: 矛盾検出**（`sources` に `original-docs` を含む場合のみ）
10. **Step 7: status.md 生成**
11. **Step 7.5: `knowledge/D{NN}-*.md` 個別生成**
12. **Step 8: 敵対的レビュー（オプション）**

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| sources | `{akm_sources}` |
| target_files | `{akm_target_files}` |
| custom_source_dir | `{akm_custom_source_dir}` |
| force_refresh | `{akm_force_refresh}` |
{akm_target_files_section}

## 入力
- `qa/*.md`（sources に qa を含む場合）
- `docs-original/*`（sources に original-docs を含む場合）
- `template/business-requirement-document-master-list.md`
- `.github/skills/knowledge-management/references/knowledge-management-guide.md`

> **知識探索の結果の取り扱い**:
> 知識源（`sources` の `workiq`、`--workiq`、`--knowledge-source`）が有効な場合、本ステップが実行される
> **前** に AKM 知識探索（FR-KD-07）が走り、`knowledge/Dxx-*.md` が既に出典付きで更新され、調べた
> 不明点と結論が `qa/*-knowledge-discovery-qa*.md` に記録されている可能性がある。本ステップでは
> 知識探索の出典付きの既存内容を **保護** し、qa/original-docs からの新規情報は差分マージのみ行うこと
> （捏造禁止・状態降格禁止）。

## 出力
- `knowledge/business-requirement-document-status.md`
- `knowledge/D{NN}-<文書名>.md`

{existing_artifact_policy}

## 完了条件
- `knowledge/business-requirement-document-status.md` が生成されている
- マッピングがある D クラスについて `knowledge/D{NN}-<文書名>.md` が生成されている
{completion_instruction}{additional_section}
