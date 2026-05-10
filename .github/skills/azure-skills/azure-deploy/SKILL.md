---
name: azure-deploy
description: >
  Execute Azure deployments for ALREADY-PREPARED applications that have existing .azure/deployment-plan.md and infrastructure files. USE FOR: run azd up, run azd deploy, execute deployment. DO NOT USE FOR: create and deploy. WHEN: run azd up、run azd deploy。
license: MIT
metadata:
  author: Microsoft
  version: 1.1.2
---
# Azure Deploy

## 目的
- Azure Deploy の適用判断と実行フローを定義する。

## トリガー
- この Skill の適用判断は frontmatter `description`（USE FOR / DO NOT USE FOR / WHEN）に従う。
- 詳細な手順・コマンド例・トラブルシューティングが必要になった時点で `references/` を参照する。

## 手順サマリ
1. 要件を確認し、対象範囲と非対象を明確化する。
2. `references/detail.md` を起点に、必要に応じて既存の `references/` 個別資料を併読する。
3. 前提条件・権限・安全条件を満たしたうえで実施する。
4. 実施後は検証結果と既知制約を記録し、後続 Skill へ必要事項を引き継ぐ。


## 必須ガードレール（本体に残置）
- 実行順は **azure-prepare → azure-validate → azure-deploy** のみ。`azure-validate` 未実施時は停止する。
- `.azure/deployment-plan.md` が存在し、`Validated` 状態でない場合は停止する。
- plan の検証状態を手動で `Validated` に変更してはならない（検証は azure-validate の責務）。
- 破壊的操作は `ask_user` による明示承認なしで実行しない。

## 詳細ガイド（Progressive Disclosure）
- 移設した詳細本文: [references/detail.md](references/detail.md)
- 追加の詳細資料: `references/` 配下
