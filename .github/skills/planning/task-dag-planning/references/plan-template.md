<!-- task_scope: single|multi -->
<!-- context_size: small|medium|large -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: true -->

> ⚠️ **コピペ後に必ず値を書き換えること（CI バリデーション必須）**
>
> | メタデータ | 値のルール |
> |-----------|-----------|
> | `task_scope` | `single`：独立して検証可能な成果物が 1 つ / `multi`：2 つ以上（分離可能） |
> | `context_size` | `small`：参照ファイル 1〜3 件 / `medium`：4〜8 件 / `large`：9 件以上または単一ファイル 500 行超 |
> | `split_decision` | task_scope=single かつ context_size が small または medium → `PROCEED`、それ以外 → `SPLIT_REQUIRED` |
> | `subissues_count` | PROCEED の場合 `0`。SPLIT_REQUIRED の場合は subissues.md の `<!-- subissue -->` ブロック数と一致させること |
> | `implementation_files` | `PROCEED` で実装ファイルを変更する場合 `true`、それ以外 `false`。**SPLIT_REQUIRED の場合は必ず `false`**（実装禁止） |
>
> SPLIT_REQUIRED の場合は以下も必須:
> - `implementation_files: false` に変更する
> - 同ディレクトリに `subissues.md` を作成し、各 Sub に `<!-- subissue -->` マーカーを付ける
> - `subissues_count` を `subissues.md` の `<!-- subissue -->` ブロック数に合わせる

# Plan: [タスク名]

## 分割判定（必須）

- task_scope: single|multi
- context_size: small|medium|large（参照ファイル数: small=1-3, medium=4-8, large=9以上または 500行超ファイル含む）
- 判定結果: PROCEED / SPLIT_REQUIRED
- 判定根拠: （以下のいずれかを記載）
    - task_scope=multi に該当（独立成果物が 2 つ以上）
    - context_size=large に該当（参照ファイル 9 件以上または 500 行超）
    - 上記いずれも非該当 → PROCEED（task_scope=single、context_size=small または medium）
- （SPLIT_REQUIRED の場合）subissues.md: 作成済み / 未作成
- （PROCEED の場合）実装に進む理由: task_scope=single、context_size=XX

---

## 前提・入力
- 入力: （入力ファイルパス）
- 出力: （出力ファイルパス）

## 作業 DAG

| ステップ | 内容 | 見積 |
|---------|------|------|
| S1 | ... | X分 |
| 合計 | | **XX分** |
