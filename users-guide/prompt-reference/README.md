# HVE Prompt 全文リファレンス

← [便利なプロンプト例](../prompt-examples.md) / [Prompt 版スニペット](../prompts/README.md) / [Workflow リファレンス](../workflow-reference.md) / [README](../../README.md)

---

> [!IMPORTANT]
> Prompt 本文の正本は、常に [`.github/prompts/**`](../../.github/prompts/) です。
> [`copies/`](./copies/) は動作確認・比較・デバッグのための **非規範な生成コピー**です。
> コピーを編集しても HVE の動作は変わりません。Prompt を変更するときは正本だけを編集し、その後にコピーと [`catalog.md`](./catalog.md) を再生成してください。
> 同期前の変更セットでは、`copies/**` / `catalog.md` を正本として扱わないでください。

## 目的

HVE がモデル、Copilot Coding Agent、Copilot SDK へ渡す固定 Prompt を `users-guide` から確認できるようにします。

- Prompt ごとの指示、禁止事項、出力形式を確認する
- 知識探索エージェントへ渡す目的・出典の規則・終える条件を確認する
- 事前・事後質問票で、どの質問と回答形式が要求されるか確認する
- Agent、Step、fan-out、runtime、Cloud の Prompt を比較する
- 正本とコピーの SHA-256 を照合し、コピーの取り違えや古い内容を検出する

全ファイルの正本・コピー有無・結線状態・SHA-256 は [`catalog.md`](./catalog.md) にあります。

## 収録範囲

`sync.py` 実行時点で実行経路に結線されている、または HVE module が読み込む `.github/prompts/**/*.prompt.md` を、相対パスの末尾へ `.txt` を付けて `copies/` へコピーしています。コピー本文は `hve.prompt_loader.load_prompt_file()` が返す UTF-8 text と同一で、改行は LF です。例えば正本 `runtime/knowledge-discovery/common.prompt.md` のコピーは `copies/runtime/knowledge-discovery/common.prompt.md.txt` です。未結線 Prompt は原則として `catalog.md` にだけ掲載し、本文はコピーしません。ただし、production 結線前に固定本文を確認する必要がある移行中の Prompt は、`sync.py` の `MIRROR_WHILE_UNWIRED` に明示したものだけをコピーします。この例外でも状態は `未結線` のままであり、production からの送信を示しません。`.txt` にする理由は、`mdq.indexer.iter_markdown()` が再帰収集する `users-guide/**/*.md` へ Prompt 本文を重複登録しないためです。

現在のファイル数、結線状態、Registry 参照数は、再生成のたびに実装から算出される [`catalog.md`](./catalog.md) 冒頭を確認してください。手書きの件数を本ページへ重複保持しません。

| 種別 | 対象 | 判定根拠 |
|---|---|---|
| Agent 本文（flat） | `.github/prompts/*.prompt.md` | `StepDef.custom_agent` |
| Step 本文 | `.github/prompts/steps/**` | `StepDef.body_template_path` |
| fan-out 追加本文 | `.github/prompts/fanout/**` | `StepDef.additional_prompt_template_path` |
| runtime Prompt | `.github/prompts/runtime/**` | production / developer / evaluation codeの `load_prompt_file()` 等 |
| Cloud 実行指示 | `.github/prompts/cloud/**` | `.github/workflows/**` のファイル参照 |

「module load のみ」は `hve/prompts.py` がファイルを読むものの、現行 production code から model へ送る参照が確認できない状態です。「未結線」は Prompt ファイルが存在するものの実行経路から参照されない状態です。module load のみの本文はコピーし、未結線の本文は `MIRROR_WHILE_UNWIRED` の明示的な移行例外だけをコピーします。該当ファイルと参照元は [`catalog.md`](./catalog.md) の「状態（静的判定）」「参照元（Registry / loader）」で確認できます。

結線状態は、`hve/workflow_registry.py` の active non-container Step、`hve/**`・`hve-dev/**`・`tools/**` の実行・開発・評価用 Prompt 参照、`.github/workflows/**` の Cloud Prompt 参照を `sync.py` が静的に照合した結果です。テストコード内だけの参照は「結線済み」の根拠に含めません。特定の run で当該分岐が実行されたことを示す runtime telemetry ではありません。

## コピーの見方

1. [`catalog.md`](./catalog.md) で対象 Prompt を検索します。
2. 「正本」で現在の編集元を、「コピー」で閲覧用スナップショットを開きます。
3. SHA-256 が一致していることを確認します。
4. `{name}`、`{{name}}`、`<run-id>` などは動的 placeholder です。実データで試す場合だけ、対象の呼び出し経路と同じ値に置換します。
5. 結果を比較するときは、Prompt 本文だけでなくモデル、実行日時、入力、利用可能な Tool、Tool 実行有無も記録します。

> [!CAUTION]
> `copies/**` は固定本文の確認用です。HVE が実際に送る最終 payload には、Agent 本文、Step 本文、fan-out 追加本文、runtime fragment、利用者入力、QA 回答、Skill 指示、実行時メタデータなどが条件に応じて追加されます。単独のコピーだけで最終 payload 全体を再現したとは判断しないでください。

## 手動デバッグでの使い分け

固定 Prompt を外部セッションへ貼り付ける確認は、HVE の Autopilot 判定や実行状態を変更しない手動デバッグです。対象 Prompt が必要とする入力ファイルや Tool を、そのセッションから利用できる場合だけ production に近い条件になります。

| 入力先 | 主に使うファイル | 確認すること |
|---|---|---|
| GitHub Copilot（CLI / VS Code Copilot Chat 等） | [`catalog.md`](./catalog.md) から選んだ `copies/**` | 必須入力の参照、該当する Tool / MCP の実行、禁止事項、出力契約 |
| Microsoft 365 Copilot Chat | 調べたい問い（知識探索の Prompt は使わない） | 知識探索が同じ問いへ到達できる出典があるか。組織データへアクセスできない場合は同等条件とみなさない |
| 知識源の MCP（Work IQ など）を使えるセッション | [`runtime/knowledge-discovery/`](./copies/runtime/knowledge-discovery/) の `common` + モード別 Prompt | Tool 実行イベント、出典の locator が応答に含まれること。`hve_*` tool は HVE のセッションにしか無いため、記録の操作は再現しない |

1. `catalog.md` で状態が `結線済み`、`ロードのみ（送信参照なし）`、`未結線` のどれかを確認します。未結線の移行用コピーは production からの送信を示しません。
2. `{name}`、`{{name}}`、`{target_content}` などの placeholder を、秘密情報を含まない試験値へ置換します。
3. 利用可能な入力ファイル、Tool / MCP、モデル、実行日時を記録してから貼り付けます。
4. 応答の内容だけでなく、入力参照、Tool 実行、出典、出力形式を期待条件と照合します。ホストが Tool 実行イベントを表示しない場合、応答の本文だけを実行証拠にせず、HVE と同等の実行と断定しません。

Microsoft 365 の実データ、個人情報、秘密情報を、このリポジトリの検証記録へ保存しないでください。手動結果を `copies/**` へ書き戻さず、Prompt を変更する場合は正本だけを編集して再同期します。

## メインタスク Prompt の合成順

`hve/runner.py::_compose_phase1_prompt()` は、条件を満たす要素だけを次の順序で連結します。

1. Agent 本文、Skill 利用ガード、Tool Search / Agentic Retrieval 方針を含む Agent prefix
2. 事前 QA がある場合の [`phase1-pre-qa-heading.prompt.md`](./copies/runtime/runner/phase1-pre-qa-heading.prompt.md.txt)、QA 回答、[`phase1-main-task-heading.prompt.md`](./copies/runtime/runner/phase1-main-task-heading.prompt.md.txt)
3. `steps/<workflow>/step-<id>.prompt.md` を基に描画された Step Prompt（該当時は fan-out 追加本文を含む）
4. 実行モード、TDD レポート、レビュー所有権の各 suffix

Agent prefix のラッパーと suffix は [`runtime/runner/`](./copies/runtime/runner/) にあります。利用者入力、Skill 利用ガード、Tool 方針、QA 回答などの動的部分は全文コピーの対象外です。

## 知識探索の確認

事前 QA、AKM、ARD の知識探索（HVE 要求定義 FR-KD）は、目的だけを与えた 1 つのセッションに読み取り専用の知識源（Work IQ などの MCP）を渡し、問い合わせの文面・回数・順序をモデルに任せます。HVE が組み立てる固定 Prompt は次の 5 件だけです。

1. [`runtime/knowledge-discovery/common.prompt.md`](./copies/runtime/knowledge-discovery/common.prompt.md.txt): 目的、使える知識源、出典の規則、終える条件（`{goal}` / `{sources}` / `{run_id}`）
2. モード別の [`qa.prompt.md`](./copies/runtime/knowledge-discovery/qa.prompt.md.txt)（事前 QA、`{qa_path}`）/ [`knowledge.prompt.md`](./copies/runtime/knowledge-discovery/knowledge.prompt.md.txt)（AKM）/ [`research.prompt.md`](./copies/runtime/knowledge-discovery/research.prompt.md.txt)（ARD）
3. 未記録の項目が残ったときの [`repair.prompt.md`](./copies/runtime/knowledge-discovery/repair.prompt.md.txt)（`{missing}`、最大 2 回）

旧 Work IQ 専用 Prompt（`runtime/workiq/**`）と合成済みテンプレート（`composed/**`）は廃止しました。応答の `STATUS:` 行や表形式は要求しません。

動作確認では次を区別してください。

- 回答の `調査状態` が `Confirmed` / `Tentative` / `Unknown` のいずれかであること。`Confirmed` には、当該セッションで成功した MCP 呼出しの応答本文に locator が含まれる出典が 1 件以上必要です（HVE が照合し、照合できない書込みは失敗として返されます）。
- 調べた結果は `qa/` の質問票の `調査回答` / `調査状態` / `調査出典` 列と `## 調査出典` 節に残ります（事前 QA は `qa/<run-id>-<step-id>-pre-execution-qa.md`、AKM / ARD は `qa/<run-id>-<label>-knowledge-discovery-qa.md`）。
- コンソールの `知識探索 [<label>]: Confirmed=… Tentative=… Unknown=… 修復=… tool失敗=…` の行で結果を確認できます。

live Microsoft 365 本文、個人情報、秘密情報を、このリポジトリの検証記録へ保存したり、MCP log から恒久文書へ転載したりしないでください。手動確認には架空データだけを使います。

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

Post-QA の先頭行や完了検証の文言を更新する場合も、編集先は `.github/prompts/runtime/qa/post-execution.prompt.md` などの正本だけです。同期前のコピーは生成された非規範スナップショットなので、手で直さず `sync.py` の再生成で揃えます。

## 同期ルール

- 編集先は `.github/prompts/**` だけです。
- `copies/**` は正本の相対パスに `.txt` を付け、本文は `load_prompt_file()` と同じ UTF-8 text（LF）を保ちます。
- 正本を変更・追加・削除した場合は、コピーと `catalog.md` を同じ変更セットで再生成します。
- `catalog.md` の SHA-256 はコピーの真正性署名ではなく、runtime text を UTF-8 bytes 化した値の不一致を同じリポジトリ内で検出するための値です。
- `.github/prompts/README.md` は運用説明であり Prompt 本文ではないため、コピー対象外です。
- `hve/tests/test_prompt_reference_contract.py` が既存の HVE test workflow から同期契約を検証します。Prompt を変更した変更セットでは、ローカルでも完了前に `sync.py --check` を実行してください。

リポジトリルートで次を実行すると、正本からコピーとカタログを再生成できます。

```text
python users-guide/prompt-reference/sync.py
```

ファイルを変更せず同期状態だけを確認する場合は、次を実行します。

```text
python users-guide/prompt-reference/sync.py --check
```
