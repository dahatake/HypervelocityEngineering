---
name: azure-kubernetes
license: MIT
metadata:
  author: Microsoft
  version: 1.1.1
description: >
  Plan, create, and configure production-ready Azure Kubernetes Service (AKS) clusters. USE FOR: create AKS environment, provision AKS environment, enable AKS observability. DO NOT USE FOR: unrelated tasks. WHEN: create AKS environment、provision AKS environment。
---
# Azure Kubernetes Service

## 目的
- Azure Kubernetes Service の適用判断と実行フローを定義する。

## トリガー
- この Skill の適用判断は frontmatter `description`（USE FOR / DO NOT USE FOR / WHEN）に従う。
- 詳細な手順・コマンド例・トラブルシューティングが必要になった時点で `references/` を参照する。

## 手順サマリ
1. 要件を確認し、対象範囲と非対象を明確化する。
2. `references/detail.md` を起点に、必要に応じて既存の `references/` 個別資料を併読する。
3. 前提条件・権限・安全条件を満たしたうえで実施する。
4. 実施後は検証結果と既知制約を記録し、後続 Skill へ必要事項を引き継ぐ。


## 必須ガードレール（本体に残置）
- Day-0（後戻り困難）と Day-1（後から変更可）を分離して判断する。
- 秘密情報（キー/トークン/接続文字列）は要求・出力しない。
- サブスクリプションIDの貼り付けを求めず、MCP/CLI でコンテキストを解決する。
- 要件が曖昧な場合、Day-0 項目は確認質問を優先する。

## 詳細ガイド（Progressive Disclosure）
- 移設した詳細本文: [references/detail.md](references/detail.md)
- 追加の詳細資料: `references/` 配下
