# `.github/prompts/`

各 Agent 名に対応する Prompt 本文（Markdown）の置き場。

## ファイル命名

`<AgentName>.prompt.md`（例: `Arch-UI-List.prompt.md`）

## 利用箇所

- **Cloud (GitHub Coding Agent)**: `create_issue` Python heredoc が Issue body の `## Custom Agent\n\`<Name>\`` セクションから Agent 名を抽出し、対応する `.prompt.md` を Issue body 末尾の `## エージェント指示（Prompt）` セクションに展開する
- **CLI (`hve`)**: `hve.prompt_loader.load_prompt(agent_name)` がメインタスク Prompt の先頭に前置する

## 新規追加手順

1. `.github/prompts/<NewAgent>.prompt.md` を作成（frontmatter なし・Markdown 本文のみ）
2. 必要なら `.github/io-contracts/<NewAgent>.yaml` も作成（schema は [SCHEMA.md](../io-contracts/SCHEMA.md) 参照）
3. `hve/workflow_registry.py` の `StepDef` で `custom_agent="<NewAgent>"` を識別子として参照
