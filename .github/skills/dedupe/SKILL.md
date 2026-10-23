---
name: dedupe
description: 利用者が /dedupe で明示的に呼ぶ、似た項目の検出とマージの入口。要求・受入基準・System Test のケース・カタログの行から意味が同じものを探し、rd-author が要求を統合し、test-designer がケースを統合・停止する。新機能は実装しない。
argument-hint: 任意: 対象の範囲（例「CASE だけ」「FR-1000 台」）。省略すると全体
disable-model-invocation: true
---

# /dedupe（似た項目の検出とマージの入口）

利用者が `/dedupe` の後に書いた文章（なければ全体）を対象に、重複した要求・受入基準・ケース・カタログの行を 1 つにまとめます。利用者は途中で応答しません。新機能の実装はしません。

0. 今のエージェントが conductor でなければ、何もせずに「Agent に conductor を選んでから、もう一度 /dedupe で送ってください」と 1 行で返して終えます。
1. conductor の手順で、次の依頼で run します（`run-state.py start --options` には下の run_options を渡します）。
   - `<request>`: 「似た項目の統合（/dedupe）。新機能は実装しない。{/dedupe の後の文章}」
   - `<run_options>`: `lane: fast`、`scope` は指定しない（空）、`git_push: しない`、`deploy: しない`、`external_write: しない`
2. 候補の検出: `python scripts/rdcheck.py similar --pairs`（種類を絞るなら `--kind FR|AC|CASE|CAT`、下限は `--min 0.35`）を実行します。同じ要求に紐づくケースどうし、同じ要求の中の AC どうしは候補に出ません。
3. 判断: 組ごとに、目的・対象エンティティ・振る舞いが同じかを読んで決めます。表現が似ているだけで目的が違う組は統合しません（理由を報告に 1 行書く）。
4. 要求・AC の統合（rd-author）: 残す要求を変更して AC を統合し、もう一方を「廃止（依頼 YYYY-MM-DD）」にします。変更履歴と決定記録に「統合: 廃止した ID → 残した ID」と書きます。廃止した AC のケースは結果の `CHANGED:` に書きます。カタログの行（CAT の組）も、統合した要求・部品に合わせて rd-author が整理します。
5. ケースの統合（test-designer）: 統合後の AC を保証するケースを 1 つに寄せ、不要になったケースは `ledger.py` 経由で停止します（`ledger.py block`。台帳は直接編集しない）。CASE の組は、残す方のケースに AC を寄せてから、もう一方を停止します。
6. 確認: `python scripts/verify.py --docs-only` が exit 0 になるまで直します。最後に `rdcheck.py similar --pairs` を再実行し、減った組の数を報告します。
7. 報告: 統合した組（残した ID ← 廃止・停止した ID）、統合しなかった組と理由、前後の組の数を書きます。
