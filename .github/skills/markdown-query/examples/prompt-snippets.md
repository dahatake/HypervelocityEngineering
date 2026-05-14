# Prompt / Custom Agent への組み込み例

## Prompt スニペット（Copilot Chat 用）

> ドキュメントに関する質問は、まず以下のコマンドで関連チャンクのみを取得してから回答してください（生 Markdown を読み込まないこと）。
>
> ```
> python -m hve.mdq search --q "<質問の主要キーワード>" --top-k 5 --max-tokens 800
> ```
>
> ヒットの `snippet` で不足する場合のみ `python -m hve.mdq get --chunk-id <ID>` で本文を取得してください。

## Custom Agent ファイル例（抜粋）

```markdown
## 入力ファイル
- 関連 Markdown は本文を直接読み込まず、`markdown-query` Skill 経由で取得すること

## 手順
1. `python -m hve.mdq stats` で索引存在を確認。未作成なら `python -m hve.mdq index`。
2. 仕様の参照が必要な箇所では `python -m hve.mdq search --q ...` を実行。
3. snippet で不足する場合のみ `get` で本文取得。
4. 引用には `path:lines` を必ず含める。
```

## Context 最小化の効果
- 既定 `--top-k 5 --max-tokens 800` で、1 回の検索あたり概ね 3KB 程度の応答に収まる（実測前提・捏造禁止のため目安）。
- 実測手段: `tools/skills/markdown-query/benchmark.py`（トークン削減率と wall-clock latency を出力、旧 `tools/measure_mdq_tokens.py` は本ツールに統合済）。
