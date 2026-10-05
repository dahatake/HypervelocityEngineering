#!/usr/bin/env bash
# Cloud Issue FormのStep入力を、各Step Issueへ渡す固定セクションへ変換する薄いadapter。

render_cloud_step_input_section() {
  local workflow_id="$1"
  local issue_body_file="$2"
  python3 -m hve.step_inputs cloud-section \
    --workflow "${workflow_id}" \
    --issue-body-file "${issue_body_file}"
}
