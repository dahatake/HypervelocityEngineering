<!-- copilot-auto-recheck-posted -->
@copilot

## 再レビュー実行指示

前回レビューで `review-verdict: FAIL` が検出されましたが、その後に修正コミットを検知しました。
最新コミットを対象に再レビューを実行してください。

 ### 要件
 1. 6軸レビュー → 修正実行 → 修正後の残存 Critical 再カウントの順で実施すること。
 2. 最終サマリーの合格判定直後に、必ず次のいずれかを出力すること。
    - `<!-- review-verdict: PASS -->`（残存 Critical = 0）
    - `<!-- review-verdict: FAIL -->`（残存 Critical > 0）
 3. レビュー結果の末尾に `Review Improvement Application` セクションを出力し、`### Modified Artifacts` と
    `### Verdict After Fix`（`<!-- review-verdict-after-fix: PASS/FAIL -->`）を必ず記載すること。
 4. 捏造は絶対に禁止です。
