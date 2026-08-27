# HVE Prompt 全文リファレンス

← [便利なプロンプト例](../prompt-examples.md) / [Prompt 版スニペット](../prompts/README.md) / [Workflow リファレンス](../workflow-reference.md) / [README](../../README.md)

---

> [!IMPORTANT]
> Prompt 本文の正本は、常に [`.github/prompts/**`](../../.github/prompts/) です。
> [`copies/`](./copies/) は動作確認・比較・デバッグのための **非規範な生成コピー**です。
> コピーを編集しても HVE の動作は変わりません。Prompt を変更するときは正本だけを編集し、その後にコピーと [`catalog.md`](./catalog.md) を再生成してください。

## 目的

HVE がモデル、Copilot Coding Agent、Copilot SDK、Work IQ へ渡す固定 Prompt を `users-guide` から確認できるようにします。

- Prompt ごとの指示、禁止事項、出力形式を確認する
- Work IQ が検索する情報源と返却形式を確認する
- 事前・事後質問票で、どの質問と回答形式が要求されるか確認する
- Agent、Step、fan-out、runtime、Cloud の Prompt を比較する
- 正本とコピーの SHA-256 を照合し、コピーの取り違えや古い内容を検出する

全ファイルの正本・コピー有無・結線状態・SHA-256 は [`catalog.md`](./catalog.md) にあります。

## 収録範囲

`sync.py` 実行時点で実行経路に結線されている、または HVE module が読み込む `.github/prompts/**/*.prompt.md` を、相対パスの末尾へ `.txt` を付けて `copies/` へ byte-for-byte でコピーしています。例えば正本 `runtime/workiq/role.prompt.md` のコピーは `copies/runtime/workiq/role.prompt.md.txt` です。未結線 Prompt は `catalog.md` にだけ掲載し、本文はコピーしません。`.txt` にする理由は、`mdq.indexer.iter_markdown()` が再帰収集する `users-guide/**/*.md` へ Prompt 本文を重複登録しないためです。

現在のファイル数、結線状態、Registry 参照数は、再生成のたびに実装から算出される [`catalog.md`](./catalog.md) 冒頭を確認してください。手書きの件数を本ページへ重複保持しません。

| 種別 | 対象 | 判定根拠 |
|---|---|---|
| Agent 本文（flat） | `.github/prompts/*.prompt.md` | `StepDef.custom_agent` |
| Step 本文 | `.github/prompts/steps/**` | `StepDef.body_template_path` |
| fan-out 追加本文 | `.github/prompts/fanout/**` | `StepDef.additional_prompt_template_path` |
| runtime Prompt | `.github/prompts/runtime/**` | production / developer / evaluation codeの `load_prompt_file()` 等 |
| Cloud 実行指示 | `.github/prompts/cloud/**` | `.github/workflows/**` のファイル参照 |

「module load のみ」は `hve/prompts.py` がファイルを読むものの、現行 production code から model へ送る参照が確認できない状態です。「未結線」は Prompt ファイルが存在するものの実行経路から参照されない状態です。module load のみの本文はコピーし、未結線の本文はコピーしません。該当ファイルと参照元は [`catalog.md`](./catalog.md) の「状態（静的判定）」「参照元（Registry / loader）」で確認できます。

結線状態は、`hve/workflow_registry.py` の active non-container Step、`hve/**`・`hve-dev/**`・`tools/**` の実行・開発・評価用 Prompt 参照、`.github/workflows/**` の Cloud Prompt 参照を `sync.py` が静的に照合した結果です。テストコード内だけの参照は「結線済み」の根拠に含めません。特定の run で当該分岐が実行されたことを示す runtime telemetry ではありません。

## コピーの見方

1. [`catalog.md`](./catalog.md) で対象 Prompt を検索します。
2. 「正本」で現在の編集元を、「コピー」で閲覧用スナップショットを開きます。
3. SHA-256 が一致していることを確認します。
4. `{name}`、`{{name}}`、`<run-id>` などは動的 placeholder です。実データで試す場合だけ、対象の呼び出し経路と同じ値に置換します。
5. 結果を比較するときは、Prompt 本文だけでなくモデル、実行日時、入力、利用可能な Tool、Tool 実行有無も記録します。

> [!CAUTION]
> `copies/**` は固定本文の確認用です。HVE が実際に送る最終 payload には、Agent 本文、Step 本文、fan-out 追加本文、runtime fragment、利用者入力、QA 回答、Skill 指示、実行時メタデータなどが条件に応じて追加されます。単独のコピーだけで最終 payload 全体を再現したとは判断しないでください。

## メインタスク Prompt の合成順

`hve/runner.py::_compose_phase1_prompt()` は、条件を満たす要素だけを次の順序で連結します。

1. Agent 本文、Skill 利用ガード、Tool Search / Agentic Retrieval 方針を含む Agent prefix
2. 事前 QA がある場合の [`phase1-pre-qa-heading.prompt.md`](./copies/runtime/runner/phase1-pre-qa-heading.prompt.md.txt)、QA 回答、[`phase1-main-task-heading.prompt.md`](./copies/runtime/runner/phase1-main-task-heading.prompt.md.txt)
3. `steps/<workflow>/step-<id>.prompt.md` を基に描画された Step Prompt（該当時は fan-out 追加本文を含む）
4. 実行モード、TDD レポート、レビュー所有権の各 suffix

Agent prefix のラッパーと suffix は [`runtime/runner/`](./copies/runtime/runner/) にあります。利用者入力、Skill 利用ガード、Tool 方針、QA 回答などの動的部分は全文コピーの対象外です。

## Work IQ の確認

QA / KM / Review の既定 Work IQ Prompt は、`hve/workiq.py::_compose_default_workiq_prompt()` が次の順序で組み立てます。

1. [`runtime/workiq/role.prompt.md`](./copies/runtime/workiq/role.prompt.md.txt)
2. [`runtime/workiq/output-schema.prompt.md`](./copies/runtime/workiq/output-schema.prompt.md.txt)
3. [`runtime/workiq/fewshot.prompt.md`](./copies/runtime/workiq/fewshot.prompt.md.txt)
4. モード別の [`qa-task.prompt.md`](./copies/runtime/workiq/qa-task.prompt.md.txt) / [`km-task.prompt.md`](./copies/runtime/workiq/km-task.prompt.md.txt) / [`review-task.prompt.md`](./copies/runtime/workiq/review-task.prompt.md.txt)
5. 対象見出しと `{target_content}`

手動テストには、同じ連結順・改行で `sync.py` が生成した次のテンプレートを使えます。

- [QA 用](./composed/workiq-qa.prompt.txt)
- [KM 用](./composed/workiq-km.prompt.txt)
- [Review 用](./composed/workiq-review.prompt.txt)

各ファイルの `{target_content}` だけを試験対象へ置換します。これらは既定 Prompt の合成結果であり、`hve.workiq.get_workiq_prompt_template()` の `config_override` を指定した実行は再現しません。

`fewshot.prompt.md` 内の氏名・日時・文書名は出力形式を示す例であり、Work IQ が取得した証拠ではありません。動作確認結果へ転記したり、`FOUND` 判定の根拠として数えたりしないでください。

Work IQ の取得結果がメインタスクへ渡される場合は、[`runtime/workiq/context-injection.prompt.md`](./copies/runtime/workiq/context-injection.prompt.md.txt) の `{context_type}` と `{workiq_context}` に差し込まれます。

ARD / AKM の専用経路は、[`ard-usecase.prompt.md`](./copies/runtime/workiq/ard-usecase.prompt.md.txt)、[`akm-ingest.prompt.md`](./copies/runtime/workiq/akm-ingest.prompt.md.txt)、[`akm-verify-update.prompt.md`](./copies/runtime/workiq/akm-verify-update.prompt.md.txt) を使用します。

動作確認では、少なくとも次を区別してください。

- `STATUS: FOUND`: 関連する一次情報が見つかった
- `STATUS: PARTIAL`: 一部の情報源だけを検索できた
- `STATUS: NOT_FOUND`: 検索できたが関連情報がなかった
- `STATUS: UNAVAILABLE`: Tool 未公開、認証失敗、タイムアウトなどで検索自体を実行できなかった

最小の確認手順は次のとおりです。

1. 検証したい質問、対象期間、期待する情報源を `{target_content}` に明記する。
2. 対応する合成済みテンプレートを、Work IQ Tool を利用できるセッションへ入力する。
3. Tool 呼び出しイベントの有無を確認する。
4. 応答の先頭 STATUS、表の情報ソース・日時・パス/場所・関連観点を入力条件と照合する。
5. 見つからない場合は `NOT_FOUND`、検索自体を実行できない場合は `UNAVAILABLE` として区別し、推測で補完しない。

`FOUND` の本文だけで取得成功を判断してはいけません。事前 QA の production 経路では、`hve/runner.py` が `tool.execution_start` から Work IQ Tool 呼び出しを確認し、かつ先頭 STATUS が `FOUND` または `PARTIAL` の場合だけ回答案へ統合します。コンソールの `Work IQ プロンプト [Qn]` / `Work IQ 応答 [Qn]` / `Work IQ ツール` 表示と、既定では `qa/<run-id>-<step-id>-workiq-pre-qa-draft.md` に保存される結果を照合してください。保存先は `workiq_draft_output_dir` 設定で変更される場合があります。Microsoft 365 の実データや個人情報を、このリポジトリの検証記録へそのまま保存しないでください。

## 質問票の確認

| 用途 | 固定 Prompt コピー | 現行状態 |
|---|---|---|
| 実行前の質問票 | [`runtime/qa/pre-execution.prompt.md`](./copies/runtime/qa/pre-execution.prompt.md.txt) | 使用中 |
| 成果物に対する質問票 | [`runtime/qa/post-execution.prompt.md`](./copies/runtime/qa/post-execution.prompt.md.txt) | 使用中 |
| 回答の統合 | [`runtime/qa/consolidate.prompt.md`](./copies/runtime/qa/consolidate.prompt.md.txt) | 使用中 |
| 統合結果の保存 | [`runtime/qa/merge-save.prompt.md`](./copies/runtime/qa/merge-save.prompt.md.txt) | module load のみ。保存処理は `QAMerger.save_merged()` が実行 |
| 質問の深さ | [`runtime/qa/questionnaire-depth-rules.prompt.md`](./copies/runtime/qa/questionnaire-depth-rules.prompt.md.txt) | module load のみ。現行の pre/post Prompt は同等の規則を本文に保持 |
| オーバーエンジニアリング禁止 | [`runtime/qa/overengineering-ban.prompt.md`](./copies/runtime/qa/overengineering-ban.prompt.md.txt) | module load のみ。現行の pre/post Prompt は同等の規則を本文に保持 |

レビュー向けの [`runtime/shared/overengineering-ban.prompt.md`](./copies/runtime/shared/overengineering-ban.prompt.md.txt) も module load のみで、現行の Review Prompt は同等の禁止事項を本文に保持しています。

質問票の出力を確認するときは、`[Qxx]`、重要度、選択肢、既定値候補、根拠、未回答時の影響が省略されていないかを正本の出力契約と照合してください。

## 同期ルール

- 編集先は `.github/prompts/**` だけです。
- `copies/**` は正本の相対パスに `.txt` を付け、本文は正本と同じ bytes を保ちます。
- 正本を変更・追加・削除した場合は、コピーと `catalog.md` を同じ変更セットで再生成します。
- `catalog.md` の SHA-256 はコピーの真正性署名ではなく、同じリポジトリ内で正本とコピーの不一致を検出するための値です。
- `.github/prompts/README.md` は運用説明であり Prompt 本文ではないため、コピー対象外です。
- 自動 CI には未接続です。Prompt を変更した変更セットでは、完了前に `sync.py --check` を実行してください。

リポジトリルートで次を実行すると、正本からコピーとカタログを再生成できます。

```text
python users-guide/prompt-reference/sync.py
```

ファイルを変更せず同期状態だけを確認する場合は、次を実行します。

```text
python users-guide/prompt-reference/sync.py --check
```
