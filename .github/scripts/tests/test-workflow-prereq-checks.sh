#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
WORKFLOWS_DIR="${REPO_ROOT}/.github/workflows"

python3 - "${WORKFLOWS_DIR}" <<'PY'
import pathlib
import re
import sys

workflows_dir = pathlib.Path(sys.argv[1])
workflow_files = sorted(
    list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
)

danger_hits = []
missing_helper_hits = []
# 危険パターン:
#   gh api /contents を stderr/stdout 両方捨てで実行し、終了コードのみで存在判定してしまう実装。
#   404 と API/通信/権限エラーを区別できず、偽 blocked を招くため禁止。
#   - gh api ... /contents/... を含むコマンド
#   - 同一コマンド内で stdout/stderr を共に /dev/null に捨てるリダイレクト
#     （例: `>/dev/null 2>&1`, `&>/dev/null`, `>/dev/null 2>/dev/null`）
#   ※ 以降は埋め込み Python の正規表現定数（PEP8 に従い大文字スネークケース）。
GH_API_WITH_LINE_CONT = r'gh\s+api(?:[^\n]*\\\n)*'
CONTENTS_PATH = r'[^\n]*?/contents/[^\n]*'
REDIRECT_CHAIN_PREFIX = r'(?:\\\n[^\n]*)*'
REDIRECT_AND_TO_NULL = r'&>\s*/dev/null'
REDIRECT_STDOUT_THEN_STDERR = r'(?:1>|>)\s*/dev/null\s+2>\s*(?:&1|/dev/null)'
REDIRECT_STDERR_THEN_STDOUT = r'2>\s*/dev/null\s+(?:1>|>)\s*/dev/null'
REDIRECT_BOTH_NULL = (
    REDIRECT_CHAIN_PREFIX + r'(?:'
    + REDIRECT_AND_TO_NULL
    + r'|'
    + REDIRECT_STDOUT_THEN_STDERR
    + r'|'
    + REDIRECT_STDERR_THEN_STDOUT
    + r')'
)
danger_pattern = re.compile(
    GH_API_WITH_LINE_CONT + CONTENTS_PATH + REDIRECT_BOTH_NULL
)
helper_source_pattern = re.compile(
    r'(^|\n)\s*(?:source|\.)\s+["\']?[^"\n]*prereq-file-check\.sh["\']?',
    re.MULTILINE,
)
activate_pattern = re.compile(r'\bactivate_with_prereq_check\b')

for wf in workflow_files:
    text = wf.read_text(encoding="utf-8")
    lines = text.splitlines()

    for m in danger_pattern.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        danger_hits.append(f"{wf}:{line_no}")

    uses_activate = False
    for line in lines:
        # YAML ワークフロー用途の簡易判定として、行内コメント以降は無視する。
        # （引用符内の # は厳密には区別しないが、当該パターンでは実害が小さい）
        code_part = line.split("#", 1)[0]
        if not code_part.strip():
            continue
        if activate_pattern.search(code_part):
            uses_activate = True
            break
    if uses_activate and not helper_source_pattern.search(text):
        missing_helper_hits.append(str(wf))

if danger_hits:
    print(
        "dangerous exit-code-only /contents API checks detected. "
        "Use prereq-file-check.sh helper to distinguish HTTP 404 from non-404 errors:"
    )
    for hit in danger_hits:
        print(f"  - {hit}")
    sys.exit(1)

if missing_helper_hits:
    print(
        "workflows calling activate_with_prereq_check() must source prereq-file-check.sh "
        "before use. Missing source statement in:"
    )
    for hit in missing_helper_hits:
        print(f"  - {hit}")
    sys.exit(1)

print("workflow prerequisite check safety: PASS")
PY
