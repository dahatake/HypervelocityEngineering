# Agent 開発コントリビューションガイド

> **対象**: `.github/agents/*.agent.md` を新規作成・更新する開発者

## frontmatter スキーマ（確定）

- **必須**
  - `name`
  - `description`
  - `metadata.version`（SemVer: `MAJOR.MINOR.PATCH`、例: `1.0.0`）
- **推奨**
  - `model`
  - `tools`
- **廃止**
  - `metadata.version` なしの旧 frontmatter 形式は受け入れない（互換 fallback なし）

## 例

```yaml
---
name: Example-Agent
description: 例示用の Agent 定義。
tools: ["*"]
metadata:
  version: "1.0.0"
---
```
