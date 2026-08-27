あなたは HVE CLI / GUI Orchestrator の workflow-level DAG wave を Fleet mode で実行します。

## Wave metadata
- workflow_id: {workflow_id}
- wave_index: {wave_index}
- repo_root_abs: {repo_root_abs}

## Fleet 実行ルール
- これは SPLIT_REQUIRED / subissues.md / GitHub Sub-Issue 作成ではありません。
- 各 worker は 1 つの DAG step だけを担当すること。
- 他 step の output_paths を編集しないこと。
- required_input_paths が存在しない場合は推測で進めず blocked として理由を書くこと。
- output_paths が指定されている場合は repository-relative path として作成・更新すること。
- 作業結果・検証結果・既知の制約を step ごとに明記すること。
- 各 worker は指定された report_dir_abs に completion-report.md を必ず作成すること。
- completion-report.md には `<!-- validation-confirmed -->` または既存の検証マーカーを含めること。
- Fleet 自己申告だけで完了とせず、HVE parent 側が completion-report.md を検証する。

## Tasks