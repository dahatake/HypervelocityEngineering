# `.github/agent-templates/`

Custom Agent 定義ファイル（`.agent.md`）の **テンプレート置き場**。

## 目的

- IDE / Copilot Chat の Custom Agent ディスパッチ一覧に **テンプレートを露出させない** ため、`.github/agents/` から分離している。
- `.github/agents/` 配下に置くと、ファイル名が `_` プレフィックスでも一部の IDE がリスト化することがあるため、ディレクトリ自体を分けている。

## 命名規則

- ファイル名: `_<purpose>.md`（先頭アンダースコアで Skill / Agent ローダから無視される慣習を兼ねる）
- 現状: `_template.md`（標準 Custom Agent 雛形）

## 使い方

1. このフォルダから `_template.md` をコピー
2. コピー先を `.github/agents/<AgentName>.agent.md` に配置
3. YAML frontmatter（`name` / `description` / `tools` 等）を埋めて利用
4. `validate-agents.py` CI が空 Skills セクション等を検証

## 関連

- `.github/copilot-instructions.md` §5 — Custom Agent との関係
- `.github/skills/agent-common-preamble/SKILL.md` — 全 Agent 共通プリアンブル
