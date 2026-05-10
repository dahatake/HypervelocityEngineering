---
name: input-file-validation
description: >
  Custom Agent の入力ファイル（必読ファイル・推奨ファイル）の存在確認と欠損時の デフォルト処理ルールを提供する。Agent が作業開始時に必読ファイル表を検証し、 欠損ファイルに対して TBD 記載で続行する。 USE FOR: input file check, missing file handling, required file validation. DO NOT USE FOR: implementation. WHEN: Agent 作業開始時の入力確認、ファイル欠損時の処理判断。
metadata:
  origin: user
  version: 1.0.0
---

# input-file-validation

## 目的

Agent が作業開始時に必読ファイル・推奨ファイルの存在を確認し、欠損時の処理を統一する。

## 基本ルール

### 必読ファイルの確認手順

1. Agent 側で定義された「必読ファイル表」を取得する
2. 各ファイルの存在を確認する
3. 欠損ファイルがある場合は「欠損時デフォルト処理」を適用する

### 欠損時デフォルト処理

- 欠損ファイルは `TBD（ファイル未検出: {パス}）` と明記する
- 該当セクションは仮定ベースで記述する（推測で埋めない）
- Agent 固有の「停止」「質問」等の処理は Agent 側でオーバーライドする

### 推奨ファイルの参照判定

- 存在すれば参照し、作業の精度を向上させる
- 存在しなくても作業は進められる
- 存在しない場合はスキップして続行する

## Agent 固有のオーバーライド

Agent 側で以下をオーバーライドできる:

- **停止**: 必読ファイルが欠損している場合に作業を中断し、ユーザーに通知する
- **質問**: 欠損ファイルについてユーザーに確認する（最大1回）
- **続行**: デフォルト動作。TBD 記載で続行する

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/missing-file-handling.md` | 欠損時デフォルト処理の詳細・Agent オーバーライドパターン |

## 入出力例

※ 以下は説明用の架空例です。

### 例1: 必読ファイルが全て存在する正常ケース

**入力**: Agent 作業開始時に必読ファイル表を検証する。必読ファイルは以下:
- `docs/company-business-requirement.md`
- `docs/catalog/service-catalog.md`

**出力**:
- `docs/company-business-requirement.md` — ✅ 存在確認済み
- `docs/catalog/service-catalog.md` — ✅ 存在確認済み
- 結果: 全ての必読ファイルが存在するため、作業を続行する

### 例2: 必読ファイルが欠損しているケース

**入力**: Agent 作業開始時に必読ファイル表を検証する。必読ファイルのうち `docs/catalog/app-catalog.md` が存在しない。

**出力**:
- `docs/company-business-requirement.md` — ✅ 存在確認済み
- `docs/catalog/app-catalog.md` — ❌ TBD（ファイル未検出: `docs/catalog/app-catalog.md`）
- 結果: 欠損ファイルを `TBD（ファイル未検出: docs/catalog/app-catalog.md）` と明記し、仮定ベースで作業を続行する

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `agent-common-preamble` | 参照元 | 全 Agent 共通 Skills 参照リストから本 Skill が呼び出される |
| `app-scope-resolution` | 併用 | docs/catalog/app-catalog.md の存在確認に本 Skill を利用 |
| `work-artifacts-layout` | 代替 | ファイル作成は work-artifacts-layout が担当 |
