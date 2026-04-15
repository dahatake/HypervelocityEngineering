<!-- estimate_total: XX -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: true -->

> ⚠️ **コピペ後に必ず値を書き換えること（CI バリデーション必須）**
>
> | メタデータ | 値のルール |
> |-----------|-----------|
> | `estimate_total` | `XX` → 実際の合計見積分数（整数）に置換。例: `12` |
> | `split_decision` | 見積 ≤ 15分 かつ 不確実性「低」 → `PROCEED`、それ以外 → `SPLIT_REQUIRED` |
> | `subissues_count` | PROCEED の場合 `0`。SPLIT_REQUIRED の場合は subissues.md の `<!-- subissue -->` ブロック数と一致させること |
> | `implementation_files` | `PROCEED` で実装ファイルを変更する場合 `true`、それ以外 `false`。**SPLIT_REQUIRED の場合は必ず `false`**（実装禁止） |
>
> SPLIT_REQUIRED の場合は以下も必須:
> - `implementation_files: false` に変更する
> - 同ディレクトリに `subissues.md` を作成し、各 Sub に `<!-- subissue -->` マーカーを付ける
> - `subissues_count` を `subissues.md` の `<!-- subissue -->` ブロック数に合わせる

# Plan: [タスク名]

## 分割判定（必須）

- 見積合計: XX 分
- 15分以下か: YES/NO
- 不確実性: 低/中/高
- 判定結果: PROCEED / SPLIT_REQUIRED
- 判定根拠: （以下のいずれかを記載）
    - 「見積合計 > 15分」に該当（XX分 > 15分）
    - 「見積合計 ≤ 15分 かつ 不確実性 中/高」に該当
    - 上記いずれも非該当 → PROCEED（見積 XX分 ≤ 15分、不確実性: 低）
- （SPLIT_REQUIRED の場合）subissues.md: 作成済み / 未作成
- （PROCEED の場合）実装に進む理由: 見積 XX分 ≤ 15分、不確実性: 低

---

## 前提・入力
- 入力: （入力ファイルパス）
- 出力: （出力ファイルパス）

## 作業 DAG

| ステップ | 内容 | 見積 |
|---------|------|------|
| S1 | ... | X分 |
| 合計 | | **XX分** |
