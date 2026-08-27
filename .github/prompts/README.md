# `.github/prompts/`

HVE がモデル / Copilot Coding Agent / Copilot SDK へ送る固定 Prompt 本文の単一正本（FR-PROMPT-SRC-01）。
Python / Workflow / shell / PowerShell は Prompt の選択・安全な読込・動的値の差し込みだけを担う。

## レイアウト

| パス | 内容 |
|---|---|
| `<AgentName>.prompt.md` | Agent 本文（flat。`load_prompt(agent_name)` 互換のため階層化しない） |
| `steps/<workflow>/step-<id>.prompt.md` | registry が参照する active Step body |
| `fanout/<workflow>/*.prompt.md` | fan-out 子 Step へ注入する追加本文 |
| `runtime/**` | QA / Review / Self-Improve / Work IQ / orchestrator / runner / GUI 等の内部 Prompt |
| `cloud/*.prompt.md` | Workflow から `@copilot` へ投稿する固定実行指示 |

## ファイル形式

- 新規作成は UTF-8 / LF / BOM なしの plain Markdown。frontmatter は付けない。
  （既存の flat Agent Prompt には BOM 付きファイルが残っており、本規定はそれらの一斉変換を要求しない）
- ファイル名は `.prompt.md` で終わること（loader が強制）。
- placeholder 記法は呼出し側の既存契約を維持する（Step body は `{name}`、fan-out は `{{key}}`）。

## 利用箇所

- **Cloud (GitHub Coding Agent)**: `create_issue` Python heredoc が Issue body の `## Custom Agent\n\`<Name>\`` セクションから Agent 名を抽出し、対応する `.prompt.md` を Issue body 末尾の `## エージェント指示（Prompt）` セクションに展開する
- **CLI (`hve`)**: `hve.prompt_loader.load_prompt(agent_name)` がメインタスク Prompt の先頭に前置する
- **Step body / 内部 Prompt**: `hve.prompt_loader.load_prompt_file(relative_path)` が唯一の読込実装（FR-PROMPT-SRC-02）。必須 Prompt の欠損・空・不正 path は model 呼出前に fail-closed で停止する

## 編集と反映

- 編集は次回 process / session から反映される（hot reload は行わない）。
- 本文をコードや Workflow へ複写しないこと。重複保持は `hve/tests/test_prompt_source_contract.py` が検出する。

## 新規追加手順

### Agent Prompt

1. `.github/prompts/<NewAgent>.prompt.md` を作成（frontmatter なし・Markdown 本文のみ）
2. 必要なら `.github/io-contracts/<NewAgent>.yaml` も作成（schema は [SCHEMA.md](../io-contracts/SCHEMA.md) 参照）
3. `hve/workflow_registry.py` の `StepDef` で `custom_agent="<NewAgent>"` を識別子として参照

### Step body / fan-out Prompt

1. `.github/prompts/steps/<workflow>/step-<id>.prompt.md`（または `fanout/<workflow>/`）を作成
2. `hve/workflow_registry.py` の `body_template_path` / `additional_prompt_template_path` にリポジトリ相対の完全パスを宣言
3. Cloud 実行を伴う場合は `.github/scripts/bash/lib/workflow-registry.sh` と `.github/scripts/powershell/lib/workflow-registry.ps1` を同じパスで更新
