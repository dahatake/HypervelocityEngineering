# 実行計画 — QA-RequirementClassifier Issue-manual-run

**作成日**: 2025-07-18
**エージェント**: QA-RequirementClassifier
**Issue識別子**: manual-run

---

## 概要

`qa/` 配下の全 `.md` ファイルを読み込み、D01〜D21 に分類し、`work/business-requirement-document-status.md` を生成する。

---

## 入力ファイル調査結果

### qa/ ディレクトリの状態

| 項目 | 結果 |
|------|------|
| `qa/` ディレクトリの存在 | **存在しない** |
| `qa/` 配下の `.md` ファイル数 | **0 件** |

> ⚠️ **重要**: `qa/` ディレクトリがリポジトリに存在しない。  
> AGENTS.md §2.2 に従い、この状態でも処理を継続し、全 D クラスを **NotStarted** として `work/business-requirement-document-status.md` を生成する。

### 参照ファイル

| ファイル | 存在確認 |
|---------|---------|
| `template/business-requirement-document-master-list.md` | ✅ 存在 |
| `.github/instructions/requirement-classification.instructions.md` | ✅ 存在 |
| `work/business-requirement-document-status.md` (既存) | ❌ 存在しない（新規作成） |

---

## 実行ステップ（DAG）

```
Step 1: 入力ファイル収集          [完了] qa/ なし → 0件確認
   ↓
Step 2: マスターリスト読み込み     [完了] D01〜D21 全21クラス取得
   ↓
Step 3: 質問項目の抽出・正規化     [完了] qa/ファイルなし → 質問数0
   ↓
Step 4: D01〜D21 マッピング        [完了] 全Dクラス: マッピング0件
   ↓
Step 5: 状態判定                   [完了] 全Dクラス: NotStarted
   ↓
Step 6: カバレッジ分析             [完了] 全21Dクラスがギャップ
   ↓
Step 7: status.md 生成             [実行予定]
```

---

## 推定所要時間

合計 5 分以内（qa/ファイルなしのため処理量が最小）

---

## 中間成果物

| ファイル | 説明 |
|---------|------|
| `work/QA-RequirementClassifier/Issue-manual-run/plan.md` | 本ファイル（実行計画） |
| `work/QA-RequirementClassifier/Issue-manual-run/artifacts/mapping-log.md` | 詳細マッピングログ |

## 最終成果物

| ファイル | 説明 |
|---------|------|
| `work/business-requirement-document-status.md` | D01〜D21 ステータス管理ファイル（新規作成） |

---

## 備考

- qa/ディレクトリが存在しない場合でも status.md を生成し、全 D クラスが NotStarted であることを明示する
- 不足判定基準 (`template/business-requirement-document-master-list.md` の `**不足判定:**` フィールド) に基づき、全 21 クラスをカバレッジギャップとして記録する
