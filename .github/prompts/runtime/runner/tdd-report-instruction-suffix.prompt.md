

## TDD report 出力先（HVE gate 必須）

この Step は HVE の TDD report gate 対象です。以下を厳守してください:

- `tdd-test-report.md` は必ず `{report_path}` に作成する。
- `Workflow` ラベルは `- Workflow: {workflow_key}` とする。 `{custom_agent}` は Agent 名であり workflow id ではない。
- `Step` ラベルは `- Step: {base_step_id}` とする。
- `Target-Key` ラベルは `- Target-Key: {target_key}` とする。
- `Phase` ラベルは `- Phase: {phase}` とする。
- Custom Agent 名のディレクトリを workflow id として使わない。
