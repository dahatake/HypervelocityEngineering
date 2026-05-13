{root_ref}

## 目的

AKM Step 1 (fan-out 21 並列) で生成された `knowledge/D01〜D21-*.md` 全体の **横断整合性レビュー** を行う。

## Custom Agent

`QA-DocConsistency`

## 入力

- 必須: `knowledge/D01-*.md` 〜 `knowledge/D21-*.md`（Step 1 の全 fan-out 子で生成された本体ファイル）
- 必須: `template/business-requirement-document-master-list.md`（必須度・最低内容の正本）
- 任意: `knowledge/business-requirement-document-status.md`（既存ステータス）

## 観点（5 観点）

1. **用語整合**: D07 用語集と他文書の語彙が一致するか（不一致は要修正候補として列挙）
2. **境界整合**: D02 スコープ × D03 ステークホルダー × D09 システムコンテキストの境界線が矛盾しないか
3. **依存整合**: D04 業務プロセス × D05 ユースケース × D10 連携契約の前後関係に矛盾がないか
4. **非機能整合**: D15 非機能要件 × D17 UAT × D21 CI/CD の数値・期限が齟齬していないか
5. **マスター不足判定**: マスターリストの各 Dxx「不足判定」条件をすべて自己点検

## 出力

1. レビューレポート（合格判定: ✅ PASS / ❌ FAIL + 観点別の指摘）
2. `knowledge/business-requirement-document-status.md` 更新（観点別の整合性ステータス追記）

{existing_artifact_policy}

## 並列実行ルール

- 本ステップは Step 1 完了後の単一ジョブ。並列ではない。
- `knowledge/` への書き込みは `work-artifacts-layout` §4.1 「削除→新規作成」遵守。

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| sources | `{akm_sources}` |
| target_files | `{akm_target_files}` |
| custom_source_dir | `{akm_custom_source_dir}` |
| force_refresh | `{akm_force_refresh}` |
{akm_target_files_section}

{completion_instruction}{additional_section}
