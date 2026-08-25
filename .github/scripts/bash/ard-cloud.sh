#!/usr/bin/env bash
# ARD Cloud Issue orchestrator. Uses workflow-registry.sh as the DAG source.
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_SCRIPT_DIR}/lib/gh-api.sh"
source "${_SCRIPT_DIR}/lib/copilot-assign.sh"
source "${_SCRIPT_DIR}/lib/issue-parser.sh"
source "${_SCRIPT_DIR}/lib/workflow-registry.sh"
source "${_SCRIPT_DIR}/lib/auto-close.sh"

_WORKFLOW_ID="ard"
_PREFIX="ARD"

_extract_section() {
  local body="$1" label="$2"
  BODY="${body}" LABEL="${label}" python3 - <<'PY'
import os
import re
body = os.environ.get("BODY", "")
label = re.escape(os.environ["LABEL"])
match = re.search(rf"###\s*{label}\s*\n+(.*?)(?=\n###|\Z)", body, re.DOTALL)
value = match.group(1).strip() if match else ""
print("" if value == "_No response_" else value)
PY
}

_has_checked() {
  local body="$1" label="$2"
  local section
  section=$(_extract_section "${body}" "${label}")
  [[ "${section}" =~ -[[:space:]]*\[[xX]\] ]]
}

_parse_initialize_context() {
  local body="$1"
  BODY="${body}" python3 - <<'PY'
import json
import os
import re
from datetime import date
from hve.workflow_registry import ARD_DEFAULT_GROUP_IDS, expand_group_step_ids

body = os.environ.get("BODY", "")

def section(label: str) -> str:
    match = re.search(rf"###\s*{re.escape(label)}\s*\n+(.*?)(?=\n###|\Z)", body, re.DOTALL)
    if not match:
        return ""
    value = match.group(1).strip()
    return "" if value == "_No response_" else value

def checked(label: str) -> bool:
    return bool(re.search(r"-\s*\[[xX]\]", section(label)))

def dropdown(label: str, default: str = "Auto") -> str:
    return section(label) or default

group_section = section("実行するグループ")
groups = re.findall(r"-\s*\[[xX]\]\s*Group\s*([1-5])\b", group_section)
if not groups:
    groups = list(ARD_DEFAULT_GROUP_IDS)
steps = []
for step_id in expand_group_step_ids("ard", groups):
    if step_id not in steps:
        steps.append(step_id)

company_name = section("対象企業名")
target_business = section("対象業務名")
error = ""
if "1" in groups and not company_name:
    error = "Group 1 requires 対象企業名"
if "2" in groups and "1" not in groups and not target_business:
    error = "Group 2 without Group 1 requires 対象業務名"

branch = section("対象ブランチ") or "main"
if (
    not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch)
    or ".." in branch
    or branch.endswith("/")
):
    error = f"invalid target branch: {branch!r}"

result = {
    "groups": groups,
    "steps": steps,
    "branch": branch,
    "company_name": company_name,
    "target_business": target_business,
    "survey_base_date": section("調査基準日") or date.today().isoformat(),
    "survey_period_years": section("調査期間年数") or "30",
    "target_region": section("対象地域") or "グローバル全体",
    "analysis_purpose": section("分析目的") or "中長期成長戦略の立案",
    "target_recommendation_id": section("対象Strategic Recommendation ID（任意）"),
    "attached_docs": section("添付資料パス（任意）") or "添付なし",
    "additional_comment": section("追加コメント（任意）"),
    "adversarial_review": checked("レビュー設定"),
    "auto_qa": checked("質問票設定"),
    "auto_merge": checked("PR完全自動化設定"),
    "qa_akm_merge": checked("Knowledge Management マージ設定"),
    "model": dropdown("使用するモデル"),
    "review_model": dropdown("レビュー用モデル（任意）"),
    "qa_model": dropdown("QA 用モデル（任意）"),
    "akm_model": dropdown("AKM 用モデル（任意）"),
    "bridge": "1" in groups and "2" in groups and not target_business,
    "error": error,
}
print(json.dumps(result, ensure_ascii=False))
PY
}

_render_step_body() {
  local step_id="$1" root_issue="$2" context_json="$3"
  CONTEXT_JSON="${context_json}" STEP_ID="${step_id}" ROOT_ISSUE="${root_issue}" python3 - <<'PY'
import json
import os
import re
from pathlib import Path

ctx = json.loads(os.environ["CONTEXT_JSON"])
step_id = os.environ["STEP_ID"]
template = Path(".github/scripts/templates/ard") / f"step-{step_id}.md"
body = template.read_text(encoding="utf-8")
root_ref = "\n".join([
    f"<!-- root-issue: #{os.environ['ROOT_ISSUE']} -->",
    f"<!-- branch: {ctx['branch']} -->",
    f"<!-- adversarial-review: {str(ctx['adversarial_review']).lower()} -->",
    f"<!-- auto-qa: {str(ctx['auto_qa']).lower()} -->",
    f"<!-- auto-merge: {str(ctx['auto_merge']).lower()} -->",
    f"<!-- qa-akm-background-merge: {str(ctx['qa_akm_merge']).lower()} -->",
    f"<!-- model: {ctx['model']} -->",
    f"<!-- review-model: {ctx['review_model']} -->",
    f"<!-- qa-model: {ctx['qa_model']} -->",
    f"<!-- akm-model: {ctx['akm_model']} -->",
    f"<!-- ard-bridge: {str(ctx['bridge']).lower()} -->",
])
policy_path = Path(".github/scripts/templates/_shared/existing-artifact-policy.md")
policy = policy_path.read_text(encoding="utf-8") if policy_path.is_file() else ""
qa_review = """## 追加コンテキストの参照

以下が存在する場合は必ず参照してください。存在しない情報は推測せず、必要に応じて不足事項として記録してください。

- `qa/` 配下の、この Root Issue / Step / PR に関連する QA 回答
- この PR または関連 Issue のレビュー指摘
- Self-Improve 結果または改善計画（存在する場合のみ）
- `## 入力` に記載された前 Step 成果物（`docs/` 成果物経由のみ。他 Step の `work/run/<run-id>/...` 配下の作業ファイルは入力として読まないこと）
- 追加で注入された既存成果物・reuse context

参照した QA / Review / Self-Improve の内容は成果物へ反映し、反映しない場合は理由を記録してください。

## 検証結果（PR本文に必須）
<!-- validation-confirmed -->
- 検証: 実行したテスト/ビルド/静的解析と結果を記載してください。"""
additional = qa_review
if ctx["additional_comment"]:
    additional += "\n\n## 追加コメント\n" + ctx["additional_comment"]
if step_id in {"1.1", "3.2"}:
    additional += (
        "\n\n## Cloud実行制約\n"
        "このCloud base Stepでは上流カタログに列挙された全キーを出現順に処理し、"
        "`{key}`を各実在キーへ置換して全成果物を生成してください。キーを捏造しないでください。"
    )
replacements = {
    "{root_ref}": root_ref,
    "{existing_artifact_policy}": policy,
    "{completion_instruction}": "- 完了時に自身に `ard:done` ラベルを付与すること",
    "{additional_section}": "\n\n" + additional,
    "{company_name}": ctx["company_name"],
    "{target_business}": ctx["target_business"],
    "{survey_base_date}": ctx["survey_base_date"],
    "{survey_period_years}": ctx["survey_period_years"],
    "{target_region}": ctx["target_region"],
    "{analysis_purpose}": ctx["analysis_purpose"],
    "{target_recommendation_id}": ctx["target_recommendation_id"],
    "{attached_docs}": ctx["attached_docs"],
}
for key, value in replacements.items():
    body = body.replace(key, str(value))
match = re.search(r"## Custom Agent\s*\n\s*`([^`]+)`", body)
if match:
    prompt_path = Path(".github/prompts") / f"{match.group(1).strip()}.prompt.md"
    if prompt_path.is_file():
        body += "\n\n## エージェント指示（Prompt）\n\n" + prompt_path.read_text(encoding="utf-8")
print(body)
PY
}

_next_steps() {
  local wf_json="$1" completed_json="$2" skipped_json="$3" active_json="$4" bridge="$5" active_labels_json="${6:-{}}"
  WF_JSON="${wf_json}" COMPLETED_JSON="${completed_json}" SKIPPED_JSON="${skipped_json}" ACTIVE_JSON="${active_json}" BRIDGE="${bridge}" ACTIVE_LABELS_JSON="${active_labels_json}" python3 - <<'PY'
import json
import os
wf = json.loads(os.environ["WF_JSON"])
completed = set(json.loads(os.environ["COMPLETED_JSON"]))
skipped = set(json.loads(os.environ["SKIPPED_JSON"]))
active = set(json.loads(os.environ["ACTIVE_JSON"]))
active_labels = json.loads(os.environ.get("ACTIVE_LABELS_JSON") or "{}")
bridge = os.environ.get("BRIDGE") == "true"
existing = {step["id"] for step in wf["steps"]}
ready = []
for step in wf["steps"]:
    sid = step["id"]
    if step.get("is_container") or sid not in active or sid in completed:
        continue
    if set(active_labels.get(sid, [])) & {"ard:ready", "ard:running", "ard:qa-ready", "ard:qa-drafting"}:
        continue
    deps = list(step.get("depends_on") or [])
    if sid == "2" and bridge:
        deps = ["1.2"]
    elif "2" in deps and "2" in skipped and step.get("skip_fallback_deps"):
        deps = list(step["skip_fallback_deps"])
    if all(dep in completed or dep in skipped or dep not in existing for dep in deps):
        ready.append(step)
print(json.dumps(ready, ensure_ascii=False))
PY
}

_activate_issue() {
  local issue_num="$1" agent="$2" branch="$3" model="$4" auto_qa="$5"
  if [[ "${auto_qa}" == "true" ]]; then
    add_label "${issue_num}" "ard:qa-ready" "${REPO}"
    return 0
  fi
  add_label "${issue_num}" "ard:ready" "${REPO}"
  if assign_copilot "${issue_num}" "${agent}" "${branch}" "" "${model}"; then
    add_label "${issue_num}" "ard:running" "${REPO}"
  else
    echo "WARNING: Copilot assignment failed for #${issue_num}" >&2
    return 1
  fi
}

initialize_ard() {
  local root_issue="$1"
  local root_json root_body context error
  root_json=$(get_issue "${root_issue}" "${REPO}")
  root_body=$(printf '%s' "${root_json}" | jq -r '.body // ""')
  context=$(_parse_initialize_context "${root_body}")
  if [[ "${SKIP_AUTO_QA:-false}" == "true" ]]; then
    context=$(printf '%s' "${context}" | jq -c '.auto_qa = false')
  fi
  error=$(printf '%s' "${context}" | jq -r '.error // ""')
  if [[ -n "${error}" ]]; then
    add_label "${root_issue}" "ard:blocked" "${REPO}" || true
    post_comment "${root_issue}" "## ⛔ ARD initialization blocked\n\n${error}" "${REPO}" || true
    echo "ERROR: ${error}" >&2
    return 1
  fi

  local branch model auto_qa adversarial auto_merge bridge
  branch=$(printf '%s' "${context}" | jq -r '.branch')
  model=$(printf '%s' "${context}" | jq -r '.model')
  auto_qa=$(printf '%s' "${context}" | jq -r '.auto_qa')
  adversarial=$(printf '%s' "${context}" | jq -r '.adversarial_review')
  auto_merge=$(printf '%s' "${context}" | jq -r '.auto_merge')
  bridge=$(printf '%s' "${context}" | jq -r '.bridge')

  create_label "auto-requirement-definition" "0E8A16" "run auto requirement definition" "${REPO}" || true
  for state in "initialized" "ready" "running" "done" "blocked"; do
    create_label "ard:${state}" "C5DEF5" "ARD ${state}" "${REPO}" || true
  done
  create_label "ard:qa-ready" "C8E6C9" "ARD QA pending" "${REPO}" || true
  create_label "ard:qa-drafting" "C8E6C9" "ARD QA drafting" "${REPO}" || true
  add_label "${root_issue}" "ard:initialized" "${REPO}"
  [[ "${adversarial}" == "true" ]] && add_label "${root_issue}" "adversarial-review" "${REPO}" || true
  [[ "${auto_qa}" == "true" ]] && add_label "${root_issue}" "auto-qa" "${REPO}" || true
  [[ "${auto_merge}" == "true" ]] && add_label "${root_issue}" "auto-approve-ready" "${REPO}" || true

  local wf_json active_json all_json skipped_json
  wf_json=$(get_workflow "ard")
  active_json=$(printf '%s' "${context}" | jq '.steps')
  all_json=$(printf '%s' "${wf_json}" | jq '[.steps[] | select(.is_container == false) | .id]')
  skipped_json=$(jq -n --argjson all "${all_json}" --argjson active "${active_json}" '$all - $active')

  declare -A issue_numbers=()
  declare -A issue_agents=()
  local count index
  count=$(printf '%s' "${wf_json}" | jq '.steps | length')
  for ((index=0; index<count; index++)); do
    local step sid title agent body labels result number node_id
    step=$(printf '%s' "${wf_json}" | jq ".steps[${index}]")
    sid=$(printf '%s' "${step}" | jq -r '.id')
    if ! printf '%s' "${active_json}" | jq -e --arg sid "${sid}" 'index($sid) != null' >/dev/null; then
      continue
    fi
    title=$(printf '%s' "${step}" | jq -r '.title')
    agent=$(printf '%s' "${step}" | jq -r '.custom_agent')
    body=$(_render_step_body "${sid}" "${root_issue}" "${context}")
    labels='["auto-requirement-definition"]'
    [[ "${adversarial}" == "true" ]] && labels=$(printf '%s' "${labels}" | jq -c '. + ["adversarial-review"]')
    [[ "${auto_qa}" == "true" ]] && labels=$(printf '%s' "${labels}" | jq -c '. + ["auto-qa"]')
    [[ "${auto_merge}" == "true" ]] && labels=$(printf '%s' "${labels}" | jq -c '. + ["auto-approve-ready"]')
    [[ -n "${model}" ]] && labels=$(printf '%s' "${labels}" | jq -c --arg label "model/${model}" '. + [$label]')
    result=$(create_issue "[ARD] Step.${sid}: ${title}" "${body}" "${labels}" "${REPO}")
    number=$(printf '%s' "${result}" | awk '{print $1}')
    node_id=$(printf '%s' "${result}" | awk '{print $2}')
    issue_numbers["${sid}"]="${number}"
    issue_agents["${sid}"]="${agent}"
    link_sub_issue "${root_issue}" "${node_id}" "${REPO}" || true
  done

  local candidates candidate_count
  candidates=$(_next_steps "${wf_json}" '[]' "${skipped_json}" "${active_json}" "${bridge}" '{}')
  candidate_count=$(printf '%s' "${candidates}" | jq 'length')
  for ((index=0; index<candidate_count; index++)); do
    local sid agent number
    sid=$(printf '%s' "${candidates}" | jq -r ".[${index}].id")
    agent="${issue_agents[${sid}]:-}"
    number="${issue_numbers[${sid}]:-}"
    [[ -z "${number}" || -z "${agent}" ]] && continue
    _activate_issue "${number}" "${agent}" "${branch}" "${model}" "${auto_qa}" || true
  done

  post_comment "${root_issue}" "## ✅ ARD initialized\n\nGroups: $(printf '%s' "${context}" | jq -r '.groups | join(", ")')\nSteps: $(printf '%s' "${active_json}" | jq -r 'join(", ")')" "${REPO}" || true
}

advance_ard() {
  local issue_num="$1"
  local issue_json title body root_issue branch bridge model auto_qa
  issue_json=$(get_issue "${issue_num}" "${REPO}")
  title=$(printf '%s' "${issue_json}" | jq -r '.title // ""')
  body=$(printf '%s' "${issue_json}" | jq -r '.body // ""')
  root_issue=$(extract_metadata "${body}" "root-issue" | tr -d '# ')
  branch=$(extract_metadata "${body}" "branch" || true); branch="${branch:-main}"
  bridge=$(extract_metadata "${body}" "ard-bridge" || true); bridge="${bridge:-false}"
  model=$(extract_metadata "${body}" "model" || true); model="${model:-Auto}"
  auto_qa=$(extract_metadata "${body}" "auto-qa" || true); auto_qa="${auto_qa:-false}"
  local step_id
  step_id=$(printf '%s' "${title}" | sed -nE 's/^\[ARD\] Step\.([0-9]+(\.[0-9]+)?):.*/\1/p')
  [[ -z "${root_issue}" || -z "${step_id}" ]] && { echo "ERROR: ARD metadata missing" >&2; return 1; }
  add_label "${issue_num}" "ard:done" "${REPO}" || true
  auto_close_issue "${issue_num}" "ARD Stepが完了したため自動クローズします。" "${REPO}" || true

  local subs wf_json active_json completed_json skipped_json labels_json
  subs=$(gh api --paginate "/repos/${REPO}/issues/${root_issue}/sub_issues?per_page=100" --jq '.')
  wf_json=$(get_workflow "ard")
  active_json=$(printf '%s' "${subs}" | jq '[.[].title | capture("^\\[ARD\\] Step\\.(?<id>[0-9]+(?:\\.[0-9]+)?):").id] | unique')
  completed_json=$(printf '%s' "${subs}" | jq --arg current "${step_id}" '[.[] | select(.state == "closed" or ([.labels[].name] | index("ard:done"))) | .title | capture("^\\[ARD\\] Step\\.(?<id>[0-9]+(?:\\.[0-9]+)?):").id] + [$current] | unique')
  local all_json
  all_json=$(printf '%s' "${wf_json}" | jq '[.steps[] | select(.is_container == false) | .id]')
  skipped_json=$(jq -n --argjson all "${all_json}" --argjson active "${active_json}" '$all - $active')
  labels_json=$(printf '%s' "${subs}" | jq '[.[] | {key: (.title | capture("^\\[ARD\\] Step\\.(?<id>[0-9]+(?:\\.[0-9]+)?):").id), value: [.labels[].name]}] | from_entries')

  local candidates count index activated=0
  candidates=$(_next_steps "${wf_json}" "${completed_json}" "${skipped_json}" "${active_json}" "${bridge}" "${labels_json}")
  count=$(printf '%s' "${candidates}" | jq 'length')
  for ((index=0; index<count; index++)); do
    local sid agent number
    sid=$(printf '%s' "${candidates}" | jq -r ".[${index}].id")
    agent=$(printf '%s' "${candidates}" | jq -r ".[${index}].custom_agent")
    number=$(printf '%s' "${subs}" | jq -r --arg sid "${sid}" '[.[] | select(.title | test("^\\[ARD\\] Step\\." + ($sid | gsub("\\."; "\\\\.")) + ":")) | .number] | first // empty')
    [[ -z "${number}" ]] && continue
    _activate_issue "${number}" "${agent}" "${branch}" "${model}" "${auto_qa}" || true
    activated=$((activated + 1))
  done

  local all_done
  all_done=$(jq -n --argjson active "${active_json}" --argjson completed "${completed_json}" '$active - $completed | length == 0')
  if [[ "${all_done}" == "true" ]]; then
    add_label "${root_issue}" "ard:done" "${REPO}"
    post_comment "${root_issue}" "## ✅ ARD completed\n\nAAS can now consume app-catalog and all APP requirement documents." "${REPO}" || true
    auto_close_root_if_all_done "${root_issue}" "${REPO}" || true
  elif (( activated == 0 )); then
    echo "ARD has pending steps but none are currently activatable." >&2
  fi
}

usage() {
  echo "Usage: ard-cloud.sh initialize|advance --issue N --repo owner/repo"
}

main() {
  local command="${1:-}" issue="" repo="${REPO:-}"
  [[ -n "${command}" ]] && shift
  while (( $# > 0 )); do
    case "$1" in
      --issue) issue="${2:?--issue requires a value}"; shift 2 ;;
      --repo) repo="${2:?--repo requires a value}"; shift 2 ;;
      *) echo "Unknown option: $1" >&2; usage >&2; return 1 ;;
    esac
  done
  [[ -z "${issue}" || -z "${repo}" ]] && { usage >&2; return 1; }
  export REPO="${repo}"
  case "${command}" in
    initialize) initialize_ard "${issue}" ;;
    advance) advance_ard "${issue}" ;;
    *) usage >&2; return 1 ;;
  esac
}

main "$@"
