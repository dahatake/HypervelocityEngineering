---
name: azure-prepare
description: >
  Prepare Azure apps for deployment (infra Bicep/Terraform, azure.yaml, Dockerfiles). USE FOR: create app, build web app, create API. DO NOT USE FOR: unrelated tasks. WHEN: create app、build web app。
license: MIT
metadata:
  author: Microsoft
  version: 1.2.9
---
# Azure Prepare

## 目的
- Azure Prepare の適用判断と実行フローを定義する。

## トリガー
- この Skill の適用判断は frontmatter `description`（USE FOR / DO NOT USE FOR / WHEN）に従う。
- 詳細な手順・コマンド例・トラブルシューティングが必要になった時点で `references/` を参照する。

## 手順サマリ
1. 要件を確認し、対象範囲と非対象を明確化する。
2. `references/detail.md` を起点に、必要に応じて既存の `references/` 個別資料を併読する。
3. 前提条件・権限・安全条件を満たしたうえで実施する。
4. 実施後は検証結果と既知制約を記録し、後続 Skill へ必要事項を引き継ぐ。


## 必須ガードレール（本体に残置）
- **Plan-first 必須**: 最初に `.azure/deployment-plan.md` を作成し、承認前に実装/実行しない。
- 破壊的操作は `ask_user` の明示承認がない限り実行しない。
- ユーザーのプロジェクト/ワークスペースディレクトリを削除しない。
- SQL Server Bicep で `administratorLogin` / `administratorLoginPassword` を生成しない（Entra-only）。

## 詳細ガイド（Progressive Disclosure）
- 移設した詳細本文: [references/detail.md](references/detail.md)
- 追加の詳細資料: `references/` 配下
