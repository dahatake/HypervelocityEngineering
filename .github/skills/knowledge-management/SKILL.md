---
name: knowledge-management
description: >
  knowledge/ 配下のファイル管理ルールを提供する。業務要件・判定表・連携契約等の ドメイン知識ドキュメントの分類・命名・更新手順を定義する。 USE FOR: knowledge/ file management, D01-D21 classification, domain knowledge organization. DO NOT USE FOR: qa/ file creation (use work-artifacts-layout). WHEN: knowledge/ 配下にファイルを作成・更新する、ドメイン知識を整理する。
metadata:
  origin: user
  version: 2.0.0
---
# knowledge-management

## 目的
- `knowledge/` 配下のドメイン知識を、D01〜D21 分類・内容合成・差分マージ・整合性確認の 4 段階で管理する。
- 主目的は `qa/` / `docs-original/` の断片を D クラス別の要求定義書ドラフトへ**内容合成**すること。単なるマッピング表作成ではなく、内容合成は省略不可。

## トリガー
- この Skill の適用判断は frontmatter `description`（USE FOR / DO NOT USE FOR / WHEN）に従う。
- `qa/` 作成、通常検証、実装・デプロイ・テストは範囲外。既存の非ゴール、SoT 優先順位、`qa/` / `docs-original/` 分岐は [`references/detail.md`](references/detail.md) を保持参照する。

## 手順サマリ
1. **分類**: Primary / Contributing を [`§2 D01〜D21 分類マッピングルール`](references/knowledge-management-guide.md#2-d01d21-分類マッピングルール) と [`§9 docs-original/ → D01〜D21 マッピングルール`](references/knowledge-management-guide.md#9-docs-original--d01d21-マッピングルール) で決める。
2. **内容合成**: [`§11 内容合成プロセス`](references/knowledge-management-guide.md#11-内容合成プロセスcontent-synthesis) に従い、Confirmed / Tentative を出典付き REQ へ統合し、Unknown は表で管理する。
3. **差分マージ**: 既存 `knowledge/D??-*.md` は [`§12 差分マージ戦略`](references/knowledge-management-guide.md#12-差分マージ戦略incremental-merge) で追記・更新・全体再生成を判断する。
4. **整合性確認**: 状態、カバー率、staleness、矛盾は [`§3`](references/knowledge-management-guide.md#3-状態判定ルール) / [`§5`](references/knowledge-management-guide.md#5-カバレッジ分析ルール) / [`§8`](references/knowledge-management-guide.md#8-staleness-check陳腐化検出) / [`§10`](references/knowledge-management-guide.md#10-矛盾検出ルール) で確認する。

不明・Conflict は推測で解決せず、上記 guide の状態判定に従う。必要な段階の参照先だけを読み、guide 全文を毎回読み込まない。
