---
name: work-artifacts-layout
description: >
  work/ 配下の作業ディレクトリ構造を、後続タスクが確実に参照できるよう整備するスキル。 USE FOR: work/ structure, artifacts path, qa/ structure, temporary file location, scratch script placement, debug output placement. DO NOT USE FOR: docs/ format (use docs-output-format). WHEN: work/ 配下にファイルを作成したい、作業ディレクトリを整備したい、一時ファイルや調査スクリプトの置き場所を決めたい。
metadata:
  origin: user
  version: 2.1.0
---

# work-artifacts-layout

## 目的
- 後続Sub/別PRが確実に参照できるよう、`work/run/<run-id>/<task>/` を「入口つき」で整理する。
  `<run-id>` は `hve.split_fork.resolve_run_id()` が採番し、env `HVE_WORK_ROOT` / `HVE_RUN_ID` で GUI/CLI/Cloud に伝播される。

## Non-goals

- **`docs/` 配下の成果物フォーマット管理** — Skill `docs-output-format` が担当
- **`src/` 配下のソースコード構造管理** — リポジトリ慣習または Agent 固有ルールに従う
- **成果物の検証** — Skill `harness-verification-loop` または通常の単回セルフチェックが担当。明示的な敵対的レビューだけ Skill `adversarial-review` を使用
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

- **Web UI 方式**: Issue 番号を run-id に流用（`work/run/issue-<N>/Issue-<N>/`）
- **CLI SDK 方式**: `<run-id>` = `<タイムスタンプ-UUID>` で分離
  - 例: `work/run/20260413T143022-a1b2c3/self-improve/step-1.1/`
- ロックファイル（`.self-improve-lock`）は run_id ディレクトリ内に配置
- `<run-id>` は `resolve_run_id()` が env > Cloud 検出 > 新規採番の順で解決

---

## work/ ディレクトリ構造（2系統）

**ベースパス**: 全て `work/run/<run-id>/` 配下に隠離される。`<run-id>` は `resolve_run_id()` で解決。

**非 Custom Agent 時**: `work/run/<run-id>/Issue-<識別子>/`  
**Custom Agent 時**: `work/run/<run-id>/<Custom Agent Name>/Issue-<識別子>/`

各ディレクトリの構成ファイル：
`README.md`・`plan.md`・`subissues.md`（分割時のみ）・`onboarding.md`（初見時のみ）・`contracts/`・`artifacts/`

**法則外パス**:
- `work/run/<run-id>/kpi/fork-kpi.jsonl` — KPI ロガーの出力先
- `work/run/<run-id>/self-improve/` — Self-Improve ループの作業 dir
- `work/archive/<run-id>.zip` — GUI cleanup_policy=archive 時のアーカイブ先（runs/ の sibling）

---

## work/run 横断参照の禁止（入力側の絶対ルール）

標準ワークフロー Step は、**他 Step の `work/run/<run-id>/...` 配下の作業成果物**（`plan.md` / `contracts/` / `artifacts/` / `completion-report.md` 等）を入力として読まないこと。

- **Step 間のデータ受け渡し**: テンプレートの `## 入力` に列挙された `docs/` 成果物経由のみとする。
- **理由**: 作業ディレクトリの `Issue-<識別子>` はモード/Agent により命名が一定でない場合があり（root-issue 番号 / APP-ID 等）、他 Step のパスを推測すると `Path does not exist` で失敗する。
- **例外**: SPLIT / Fleet サブタスクは、コードが明示注入する `dependency_completion_reports` の絶対パスのみを参照する（パスの自力推測は禁止）。

根拠: `.github/copilot-instructions.md` §0「work/run 横断参照の禁止（絶対）」。

---

## 一時作業ファイルの配置先（ルート直下作成の禁止）

一時作業ファイル（調査スクリプト・デバッグ出力・コマンドログ・プローブ・実験の中間データ・退避コピー）は
**リポジトリルート直下（`/`）に作成してはならない**。必ず `work/` 配下に作成する。

| 用途 | 禁止される配置 | 正しい配置 |
|---|---|---|
| 使い捨ての調査・検証スクリプト | `/_tmp_probe.py` | `work/run/<run-id>/<task>/artifacts/probe.py` |
| コマンド出力・テストログの退避 | `/pytest_out.txt` | `work/run/<run-id>/<task>/artifacts/pytest.log` |
| 実験・比較の中間データ | `/tmp/` `/MagicMock/` | `work/run/<run-id>/<task>/artifacts/` |
| 調査メモ・決定事項 | `/notes.md` | `work/run/<run-id>/<task>/contracts/` |

- **`.gitignore` 済みかどうかは判断基準にならない**。ignore されていても作業ツリーは汚れ、後続 Agent の探索コストになるため禁止対象。
- ルート直下へ新規ファイル／ディレクトリを追加してよいのは、許可リストに載るリポジトリ標準ファイルのみ。許可リストの正本は `.github/workflows/protect-readonly-paths.yml` の `ROOT_FILE_ALLOWLIST` / `ROOT_DIR_ALLOWLIST` で、`check-root-temp-files` ジョブが PR で違反を fail させる。正当な追加が必要な場合は同じ PR で許可リストも更新する。
- テストやツールが cwd 依存でファイルを書く場合は、`tmp_path` 等で出力先を明示し、ルート直下へ書かせないこと（`unittest.mock` の `MagicMock` をパスとして扱うと `MagicMock/` ディレクトリが生成される事故が起きる）。

根拠: `.github/copilot-instructions.md` §0「一時作業ファイルは `work/` 配下に限定（絶対）」。

---

## 恒久成果物からの work/ 出典引用の禁止（2026-08-05 追加）

`work/` はジョブ完了後に削除されてよい使い捨て領域である。恒久的な成果物（`docs/**`, `knowledge/**`, `qa/**`, `src/**`, `docs-generated/**`, `hve-dev/**`, `users-guide/**` 等）が `work/` 配下のパスをリンクやコードスパンで出典として引用すると、`work/` 削除後にリンク切れ・再現不能な事実が残る。

- **禁止**: 上記の恒久成果物から `work/` 配下のパスへの出典引用（Markdown リンク・コードスパン中のパス文字列を問わない）。
- **唯一の例外**: `CHANGELOG.md`。ただし `work/` へのパス／リンクは禁止し、伝えたい内容は要約文字列として本文に直接記載すること。
- **対象外**（禁止しない）: `work/` 自体の構造・ライフサイクル・パス規約そのものを説明する記述（本 Skill や `copilot-instructions.md` の記述など）。これは「`work/` を出典として使う」のではなく「`work/` という仕組みを説明する」ものであるため区別する。
- **修正方針**: 引用元がリンク切れなら捏造せず消失の事実を明記する。引用元が現存し、かつ引用先の周辺に同等の内容が既に文章化されていれば、パス参照だけを削除する（内容の重複追加はしない）。周辺に内容がなく要約が必要な場合は、引用元を読み実在する事実だけを短く要約してその場に記載する。

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

**例1（非 Custom Agent: Issue #42）**: `work/run/issue-42/Issue-42/` に README.md + plan.md + contracts/ + artifacts/

**例2（Custom Agent: Arch-DataModeling + Issue #58）**: `work/run/issue-58/Arch-DataModeling/Issue-58/`

**例3（qa/ 命名）**: Custom Agent + Issue #58 → `qa/Arch-DataModeling-Issue-58.md`

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-dag-planning` | 利用元 | plan.md / subissues.md の配置に本Skillのパス規則を使用 |
| `large-output-chunking` | 利用元 | artifacts/ 配下の分割ファイル配置に本Skillの構造を使用 |
| `docs-output-format` | 補完 | docs/ 配下のフォーマットは docs-output-format が担当 |
| `task-questionnaire` | 利用元 | qa/ 配下の質問票ファイル管理に本Skillの§4.3を使用 |
