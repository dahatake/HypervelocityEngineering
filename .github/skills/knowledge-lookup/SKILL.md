---
name: knowledge-lookup
description: >
  knowledge/ 配下の確定済みドメイン知識ドキュメント（D01〜D21）を参照する。 USE FOR: checking business rules, verifying glossary definitions, reviewing data model specifications. DO NOT USE FOR: creating or updating knowledge/ files (use knowledge-management skill). WHEN: during task execution、business requirements。
metadata:
  origin: user
  version: 0.1.0
---
# knowledge-lookup

## 適用判断

入力に十分な情報があれば参照不要。不明瞭・欠落・矛盾が残る箇所だけを調べる。判断に迷う場合は [不明瞭の判断基準](references/detail.md#不明瞭の判断基準) を参照する。

## 参照と採用

1. Agent が指定した D 番号の直接参照を優先する。未指定なら `knowledge/business-requirement-document-status.md` または [D01〜D21 カテゴリ参照ガイド](references/detail.md#d01d21-カテゴリ参照ガイド) で絞り込む。
2. 該当する `knowledge/D{NN}-*.md` を [参照手順](references/detail.md#参照手順) に従って読む。`knowledge/` は読み取り専用とし、全件読込や自動更新は行わない。
3. 状態ラベルがあれば Confirmed を採用し、Tentative / Unknown / Conflict は未確定として扱う。ラベルがない場合は記載を参照できるが、TBD は未確定のまま保持する。
4. 根拠不足・該当情報なしの場合は [既存の停止・TBD 分岐](references/detail.md#step-5-情報が見つからなかった場合の振る舞い段階的ルール) に従う。情報のない箇所を推測で埋めない。
