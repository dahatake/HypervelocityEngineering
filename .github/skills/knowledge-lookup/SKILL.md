---
name: knowledge-lookup
description: >
  knowledge/ 配下の確定済みドメイン知識ドキュメント（D01〜D21）を参照する。 USE FOR: checking business rules, verifying glossary definitions, reviewing data model specifications. DO NOT USE FOR: creating or updating knowledge/ files (use knowledge-management skill). WHEN: during task execution、business requirements。
metadata:
  origin: user
  version: 0.1.0
---
# knowledge-lookup

## 目的
- knowledge-lookup の適用判断と実行フローを定義する。

## トリガー
- この Skill の適用判断は frontmatter `description`（USE FOR / DO NOT USE FOR / WHEN）に従う。
- 詳細な手順・コマンド例・トラブルシューティングが必要になった時点で `references/` を参照する。

## 手順サマリ
1. 要件を確認し、対象範囲と非対象を明確化する。
2. `references/detail.md` を起点に、必要に応じて既存の `references/` 個別資料を併読する。
3. 前提条件・権限・安全条件を満たしたうえで実施する。
4. 実施後は検証結果と既知制約を記録し、後続 Skill へ必要事項を引き継ぐ。

## 詳細ガイド（Progressive Disclosure）
- 移設した詳細本文: [references/detail.md](references/detail.md)
- 追加の詳細資料: `references/` 配下
