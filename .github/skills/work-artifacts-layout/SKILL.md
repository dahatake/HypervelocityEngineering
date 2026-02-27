---
name: work-artifacts-layout
description: "AGENTS.mdのwork/<task>/構造を、読みやすく運用できるように整える。README.md の入口設計や contracts/artifacts の分け方が必要なときに使う。"
---

# work-artifacts-layout

## 目的
- 後続Sub/別PRが確実に参照できるよう、work/<task>/ を「入口つき」で整理する。

## 運用ルール
- README.md を“入口”として最初に整備（何を見れば良いかを明示）
- 契約/決定事項は contracts/ に集約（根拠のパスを必ず付ける）
- 生成物/抽出物は artifacts/ に集約（巨大なら large-output-chunking に従う）
- 長文メモは notes.md に逃がし、PRには要約だけを書く

## README.md（入口）最小テンプレ
- 目的
- 入口（plan / contracts / artifacts）
- 根拠（参照元）
- 現状（完了/未完/次のSub）
- 検証（実行したこと、できない場合の理由）
