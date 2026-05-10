---
name: work-artifacts-layout
description: >
  work/ 配下の作業ディレクトリ構造を、後続タスクが確実に参照できるよう整備するスキル。 USE FOR: work/ structure, artifacts path, qa/ structure. DO NOT USE FOR: docs/ format (use docs-output-format). WHEN: work/ 配下にファイルを作成したい、作業ディレクトリを整備したい。
metadata:
  origin: user
  version: 2.0.0
---

# work-artifacts-layout

## 目的
- 後続Sub/別PRが確実に参照できるよう、work/<task>/ を「入口つき」で整理する。

## Non-goals

- **`docs/` 配下の成果物フォーマット管理** — Skill `docs-output-format` が担当
- **`src/` 配下のソースコード構造管理** — リポジトリ慣習または Agent 固有ルールに従う
- **成果物の品質評価・レビュー** — Skill `adversarial-review` が担当
- **質問票の内容設計** — Skill `task-questionnaire` が担当

## 運用ルール
- README.md を"入口"として最初に整備
- 契約/決定事項は contracts/ に集約（根拠のパスを必ず付ける）
- 生成物/抽出物は artifacts/ に集約（巨大なら large-output-chunking に従う）

## README.md（入口）最小テンプレ
目的 / 入口（plan / contracts / artifacts）/ 根拠（参照元）/ 現状（完了/未完/次のSub）/ 検証

---

## §4.1 絶対ルール概要（詳細: `references/directory-structure-detail.md`）

`work/` および `qa/` 配下のファイル作成・更新時は **delete→create** に必ず従うこと。

- **禁止**: 上書き更新(edit/update/patch) / 追記(append) / 削除省略
- **適用範囲**: `work/` 全ファイル / `qa/` 全ファイル / `knowledge/` 全ファイル / 全 Custom Agent

---

## 並列安全性ルール

複数ジョブが同時実行される場合、各ジョブは以下の識別子でディレクトリを分離する:

- **Web UI 方式**: Issue 番号（`Issue-<N>`）で自動分離（変更不要）
- **CLI SDK 方式**: `run-<タイムスタンプ-UUID>` + `step-<step_id>` で分離
  - 例: `work/self-improve/run-20260413T143022-a1b2c3/step-1.1/`
- ロックファイル（`.self-improve-lock`）は `run_id` ディレクトリ内に配置
- `run_id` は `SDKConfig.run_id` フィールドで管理し、`run_workflow()` 開始時に1回生成する

---

## work/ ディレクトリ構造（2系統）

**非 Custom Agent 時**: `work/Issue-<識別子>/`  
**Custom Agent 時**: `work/<Custom Agent Name>/Issue-<識別子>/`

各ディレクトリの構成ファイル：
`README.md`・`plan.md`・`subissues.md`（分割時のみ）・`onboarding.md`（初見時のみ）・`contracts/`・`artifacts/`

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/directory-structure-detail.md` | §4.1 疑似コード全体、§4.3 qa/ の構造・命名規則・適用対象、§4.4 ソースコードパス標準定義テーブル |

---

## 成果物サマリーテンプレート（Observation Quality）

全 Agent の成果物に以下 4 要素を含める（PR description 内に統合して記載する）:

```
## 成果物サマリー
- status:       [成功/失敗/部分完了]
- summary:      [何を行い何が変わったか（3行以内）]
- next_actions: [後続で必要な作業（あれば Agent 名を推奨付き）]
- artifacts:    [生成/変更したファイルの一覧]
```

§7 との関係: 本テンプレートは §7「目的/変更点/影響範囲/検証結果/既知の制約/次にやるSub」の構造化補完版。PR description 内に統合して記載する。

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（非 Custom Agent: Issue #42）**: `work/Issue-42/` に README.md + plan.md + contracts/ + artifacts/

**例2（Custom Agent: Arch-DataModeling + Issue #58）**: `work/Arch-DataModeling/Issue-58/`

**例3（qa/ 命名）**: Custom Agent + Issue #58 → `qa/Arch-DataModeling-Issue-58.md`

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-dag-planning` | 利用元 | plan.md / subissues.md の配置に本Skillのパス規則を使用 |
| `large-output-chunking` | 利用元 | artifacts/ 配下の分割ファイル配置に本Skillの構造を使用 |
| `docs-output-format` | 補完 | docs/ 配下のフォーマットは docs-output-format が担当 |
| `task-questionnaire` | 利用元 | qa/ 配下の質問票ファイル管理に本Skillの§4.3を使用 |
