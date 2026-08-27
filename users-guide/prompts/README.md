# Prompt 版 スニペット索引

← [Prompt 版 はじめかた](../hve-prompt-getting-started.md) / [README](../../README.md)

---

**そのまま貼り付けて使える** 依頼文の索引です。
使い方の全体像は [hve-prompt-getting-started.md](../hve-prompt-getting-started.md) を参照してください。

HVE が内部で使用する Agent / Step / Work IQ / 質問票 / Review / Cloud Prompt の固定本文を確認する場合は、[HVE Prompt 全文リファレンス](../prompt-reference/README.md) を参照してください。本文の正本は `.github/prompts/**` で、リファレンス側はデバッグ用の生成コピーです。

> **あなたがコマンドを打つ必要はありません。** 実行計画（plan）の取得と実行は Copilot が代行します。
> 貼り付け用の完全な依頼文には、いずれも「まず実行計画だけを見せる。私が『実行してください』と
> 書くまで実行しない」を含めています。この 2 文を消さないでください
>（Step を絞る差分だけを示す断片例は除く）。

---

## 目次

- [共通テンプレート](#共通テンプレート)
- [プレースホルダ規約](#プレースホルダ規約)
- [Workflow 別スニペット](#workflow-別スニペット)
- [貼り付ける前のチェック](#貼り付ける前のチェック)

---

## 共通テンプレート

```text
HVE の Prompt 版で作業してください。

- 目的: <なにを作りたいか / 何を判断したいか>
- Workflow: <workflow_id>
- Step: <step_id, step_id>            # 省略可。省略時は既定の選択
- パラメータ: <name>=<value>          # Workflow が宣言している名前だけ
- 入力: <canonical> は <実ファイル> にあります   # 省略可（入力別名）
- 制約: <やってほしくないこと>
- 期待する成果物: <どのファイルが増えるか>

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## プレースホルダ規約

| 表記 | 置き換えるもの | 置き換えないと |
|---|---|---|
| `<workflow_id>` | `hve/workflow_registry.py` の canonical ID | request が拒否される |
| `<step_id>` | 当該 Workflow に実在する Step ID | request が拒否される |
| `APP-NNN` | `docs/catalog/app-catalog.md` の APP-ID | 対象が特定できず Copilot が質問する |
| `<resource-group>` | Azure リソースグループ名 | デプロイ系 Step で質問される |
| `<canonical>` / `<実ファイル>` | 入力別名の対応（[custom-inputs.md](custom-inputs.md)） | 別名が適用されない |

**推測で埋めないでください。** 分からない項目は書かずに残せば、Copilot が質問します。

---

## Workflow 別スニペット

| ファイル | 対象 Workflow | 主な用途 |
|---|---|---|
| [requirements-architecture.md](requirements-architecture.md) | `ard` / `aas` / `ada` | 企業・業務分析、アプリ構成設計、AI Agent 向けデータ設計 |
| [web-application.md](web-application.md) | `aad-web` / `asdw-web` | Web 画面・API の設計と、実装・デプロイ |
| [dataflow.md](dataflow.md) | `adfd` / `adfdv` | バッチ処理の設計と、実装・デプロイ |
| [ai-agent.md](ai-agent.md) | `aag` / `aagd` / `aar` | AI Agent の設計・実装、Agentic Retrieval の後付け |
| [knowledge-management.md](knowledge-management.md) | `akm` | `qa/` / `docs-original/` から `knowledge/` を生成・更新 |
| [design-doc-ingestion.md](design-doc-ingestion.md) | `adi` | 既存設計書の取り込みと質問票生成 |
| [source-code-documentation.md](source-code-documentation.md) | `adoc` | 既存コードからの技術ドキュメント生成 |

### 横断・特殊ケース

| ファイル | 用途 |
|---|---|
| [cross-workflow.md](cross-workflow.md) | 複数 Workflow を依存順にまとめて計画する |
| [custom-inputs.md](custom-inputs.md) | 入力ファイル名が canonical と違うときの指定方法 |

Workflow ID と成果物の対応は [workflow-reference.md](../workflow-reference.md) と
`hve/workflow_registry.py` が正本です。

---

## 貼り付ける前のチェック

- [ ] （任意）GUI で設定を保存した（モデル等。未保存なら既定値）
- [ ] Workflow ID を canonical 表記で書いた
- [ ] Azure へのデプロイを含むかどうかを制約に明記した
- [ ] APP-ID / リソースグループなど、必要なパラメータを埋めた（分からないものは空欄のまま）
- [ ] 「まず実行計画だけを見せる。承認するまで実行しない」の 2 文が残っている
