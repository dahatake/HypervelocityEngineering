{root_ref}

## 目的

ADI Step 1.1 で生成された D01〜D21 の 21 成果物を join し、横断整合性レビュー済みの原本質問票へ統合する。

## モード

`original-docs-questionnaire`

## Custom Agent

`QA-DocConsistency`

## 入力（必須）

- `qa/D01-original-docs-questionnaire.md`
- `qa/D02-original-docs-questionnaire.md`
- `qa/D03-original-docs-questionnaire.md`
- `qa/D04-original-docs-questionnaire.md`
- `qa/D05-original-docs-questionnaire.md`
- `qa/D06-original-docs-questionnaire.md`
- `qa/D07-original-docs-questionnaire.md`
- `qa/D08-original-docs-questionnaire.md`
- `qa/D09-original-docs-questionnaire.md`
- `qa/D10-original-docs-questionnaire.md`
- `qa/D11-original-docs-questionnaire.md`
- `qa/D12-original-docs-questionnaire.md`
- `qa/D13-original-docs-questionnaire.md`
- `qa/D14-original-docs-questionnaire.md`
- `qa/D15-original-docs-questionnaire.md`
- `qa/D16-original-docs-questionnaire.md`
- `qa/D17-original-docs-questionnaire.md`
- `qa/D18-original-docs-questionnaire.md`
- `qa/D19-original-docs-questionnaire.md`
- `qa/D20-original-docs-questionnaire.md`
- `qa/D21-original-docs-questionnaire.md`

## 観点

1. 21 成果物間の質問重複・矛盾を統合
2. 横断観点（用語整合・境界整合・依存整合・非機能整合）の追加質問抽出
3. 優先度の再評価

## 出力

- `qa/original-docs-cross-questionnaire.md`

## 完了条件

- D01〜D21 の 21 成果物を全件読み、重複・矛盾・横断論点を統合している
- `qa/original-docs-cross-questionnaire.md` が生成されている
- 統合後の質問が 0 件の場合も、サマリーに `総質問数: 0` と `質問なし` を明記している

{completion_instruction}{additional_section}

{existing_artifact_policy}