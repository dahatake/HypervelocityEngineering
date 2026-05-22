{root_ref}

## 目的

AQOD Step 1 (fan-out 21 並列) で生成された各 `qa/{{key}}-original-docs-questionnaire.md` の **横断整合性レビュー** を実施し、original-docs 全体の質問票として統合する。

## Custom Agent

`QA-DocConsistency`

## 入力（必須）

- `qa/D01-*-questionnaire.md` 〜 `qa/D21-*-questionnaire.md`（Step 1 全 fan-out 子の成果物）
- `template/business-requirement-document-master-list.md`

## 観点

1. 質問の重複・矛盾を統合
2. 横断観点（用語整合・境界整合・依存整合・非機能整合）の追加質問抽出
3. 優先度の再評価

## 出力

- `qa/original-docs-cross-questionnaire.md`

{completion_instruction}{additional_section}

{existing_artifact_policy}
