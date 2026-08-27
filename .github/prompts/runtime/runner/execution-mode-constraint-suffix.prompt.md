

## 実行モード制約

本実行は CLI / GUI Orchestrator 配下です。次のルールを厳守してください:

- `task_scope` / `context_size` による SPLIT_REQUIRED 判定は **行わない**。
- 宣言された `output_paths` の主成果物を **必ず生成してから終了** すること。
- `plan.md` / `subissues.md` のみを出力して終了することは **禁止**（後続 Step が成果物不在で skip / 失敗する）。
