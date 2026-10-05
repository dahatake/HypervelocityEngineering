# Workflow / Step へ任意の文書を渡す

HVEでは、既存の入出力契約を変更せず、実行するStepへ任意の文書を**追加資料**または**欠損入力の代替資料**として渡せます。Cloud / GUI / CLI / Promptの4面で同じStep入力bundleを使用します。

## 対象と制約

- Localの対象は、registryに登録された13 Workflowの全non-container Stepです。container Stepを選ぶと子の実行Stepへ展開されます。
- Cloudの対象は、Issue Formを持つ現行12 Workflowです。local専用の`adi`はCloud対象になりません。
- Stepごとの表示情報は`.github/io-contracts/<Agent>--<workflow>--<step>.yaml`、実行時必須入力は`StepDef.required_input_paths`が正本です。
- 追加資料は文書入力の有無にかかわらず複数指定できます。
- 代替資料を指定できるのは、canonical文書が欠損している場合だけです。既存canonicalは上書きしません。
- directory、JSON、script、runtime parameter、native pipeline input、system instruction、Skillは代替できません。

選択順は保持されます。原本は変更されず、Markdown以外のPDF / Word / Excel / PowerPoint等は既存のMicrosoft MarkItDown経路でMarkdown化され、現在の`work/run/<run-id>/...`配下へ保存されます。bundleには`workflow_id`、`step_id`、`role`、`canonical`、materialize後の`actual`、内容のSHA-256が記録されます。

## GUI

1. Step 1でWorkflowと実行Stepを選択します。
2. 右ペインの「Step入力（run-scoped）」でrequired / optional、canonical、kind、existing / missingを確認します。
3. 各Stepの「追加資料を選択…」、または欠損文書の「代替資料を選択…」から複数ファイルを選びます。
4. `docs-original/`候補検索も利用できます。候補は自動選択されません。
5. 変換予定のMarkdown名と選択順を確認して実行します。

この選択はrun-scopedであり、GUIの永続設定には保存されません。

## CLI

対話型の`python -m hve cli`では、Step選択後にStep入力wizardが候補検索、追加 / 代替、複数選択を案内します。不要な場合は何も選ばず従来どおり実行できます。

non-interactiveでは`--step-input`を指定順に繰り返します。

```text
--step-input <step-id> <additional|substitute> <canonical|-> <source>
```

- `additional`のcanonicalは`-`で省略できます。
- `substitute`では欠損している代替可能なcanonicalを指定します。
- `source`はlocalの明示パスを使用できます。
- wizardを表示しない場合は`--no-step-input-wizard`を使用します。

## Prompt

Prompt request v1の各`workflows[]`へ任意の`step_inputs`を追加します。省略時は従来動作です。

```json
{
  "workflow_id": "aas",
  "steps": ["1"],
  "step_inputs": [
    {
      "step_id": "1",
      "role": "additional",
      "source": "incoming/context.pdf"
    },
    {
      "step_id": "1",
      "role": "substitute",
      "canonical": "docs/catalog/app-catalog.md",
      "source": "incoming/app-catalog.docx"
    }
  ]
}
```

Prompt planのSHA-256には、正規化済みbundleの内容・順序・role・canonical / actual対応・digestが含まれます。plan提示後にいずれかが変わるとstaleになり、再planと再承認が必要です。同じcanonicalへ既存`input_aliases`とStep入力を重ねることはできません。

## Cloud

現行12 Issue Formには次の任意textareaがあります。

- **Step Input Files**: 1行に1ファイル。対象branchに存在するbranch-relative pathを記載します。Issue Formへファイルをドラッグした場合はMarkdown upload linkになります。
- **Step Input Bindings**: 1行に1つのJSON object。`step_id`、`role`、1始まりの`file`、必要時の`canonical`を指定します。

```jsonl
{"step_id":"1","role":"additional","file":1}
{"step_id":"2.1","role":"substitute","file":2,"canonical":"docs/example.md"}
```

共通helperは固定Cloud Promptを各Step Issueへ渡し、Agentが`python3 -m hve.step_inputs cloud-manifest`でbranch上の資料をrun-scopedにmaterializeします。

現時点ではupload downloaderを実装していません。upload linkを受け取ると`Cloud upload unavailable`でfail-closedとなります。URLを推測取得せず、同じ資料を対象branchへ置き、branch-relative pathへ変更してください。Cloudがupload対応済みであるとは表示しません。

## 事前QAとMCP同意

custom inputを1件以上持つStepでは、保存済みの`auto_qa`設定を変更せず、そのrunだけ事前QAを実効有効化します。

- 質問が0件ならメインタスクへ進みます。
- 質問が1件以上あり、安全なadapterがreadyの場合だけ、queryより前にexact **`MCP経由で情報を補填しますか?`** と確認します。
- 明示同意後に限り、usable な知識源 MCP（例: exact `workiq` と allowlist の `ask` など）を知識探索で使用します。
- 知識探索が `調査回答` / `調査状態` / `調査出典` を埋め、`Confirmed` / `Tentative` で回答が空でないものだけを回答済みQAへ統合します。取得不能・未検証・出典検証不合格は既定値候補へ戻します。
- Cloudで安全なOAuth remote MCP対話が成立しない場合は従来の手動QAへ戻します。

## エラー時の確認

- `canonical入力が既に存在`: `substitute`ではなく`additional`を使用します。
- `対応文書形式ではありません`: PDF / Office / Markdown等の対応文書を指定します。
- `SHA-256が一致しません`: materialize後に文書が変わっています。再plan / 再実行します。
- `input_aliasと競合`: 同じcanonicalにはStep入力か`input_aliases`の一方だけを使います。
- `Cloud upload unavailable`: upload URLではなく対象branchのbranch-relative pathを指定します。
