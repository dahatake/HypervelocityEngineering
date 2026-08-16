#!/usr/bin/env bash
# MT-02: install-macos.sh static RED contract test.
#
# Safety contract for this test:
# - Never source or execute install-macos.sh (bash -n only).
# - Never access the network, invoke sudo, or perform an installation.
# - Inspect executable source rather than accepting full-line comments as evidence.

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AIRGAP_KIT_DIR="$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd)"
SUT="${AIRGAP_KIT_DIR}/install-macos.sh"

if [[ ! -e "${SUT}" ]]; then
    printf 'RED: required macOS installer is not implemented: %s\n' "${SUT}" >&2
    printf 'Expected by CONTRACT.md as the canonical lowercase path: install-macos.sh\n' >&2
    exit 1
fi

if [[ ! -f "${SUT}" ]]; then
    printf 'RED: macOS installer path is not a regular file: %s\n' "${SUT}" >&2
    exit 1
fi

# Parse only; do not execute the installer under test.
if ! bash -n "${SUT}"; then
    printf 'RED: install-macos.sh has invalid Bash syntax\n' >&2
    exit 1
fi

if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys' >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1 && python -c 'import sys' >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    printf 'RED: Python is required to run this static source test\n' >&2
    exit 1
fi

"${PYTHON_BIN}" - "${SUT}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

sut = Path(sys.argv[1])
source = sut.read_text(encoding="utf-8")


def strip_shell_comments(text: str) -> str:
    """Remove shell comments while preserving quoted hashes and line layout."""
    cleaned: list[str] = []
    for line in text.splitlines():
        single = False
        double = False
        escaped = False
        cut = len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\" and not single:
                escaped = True
                continue
            if char == "'" and not double:
                single = not single
                continue
            if char == '"' and not single:
                double = not double
                continue
            if (
                char == "#"
                and not single
                and not double
                and (index == 0 or line[index - 1].isspace())
            ):
                cut = index
                break
        cleaned.append(line[:cut])
    return "\n".join(cleaned)


code = strip_shell_comments(source)
flags = re.IGNORECASE | re.MULTILINE | re.DOTALL
failures: dict[int, list[str]] = {number: [] for number in range(1, 9)}


def has(pattern: str) -> bool:
    return re.search(pattern, code, flags) is not None


def has_any(*patterns: str) -> bool:
    return any(has(pattern) for pattern in patterns)


def require(group: int, condition: bool, message: str) -> None:
    if not condition:
        failures[group].append(message)


def reject(group: int, pattern: str, message: str) -> None:
    if has(pattern):
        failures[group].append(message)


fail_closed = has_any(
    r"\b(?:die|fatal|abort|fail)\s*\(\s*\)",
    r"\bexit\s+[1-9][0-9]*\b",
    r"\braise\s+(?:SystemExit|RuntimeError|ValueError)\b",
)

# (1) macOS 14+ / arm64 / manifest schema and target guards.
require(1, has(r"\buname\b[^\n]*-s") and has(r"(?:if|elif|case|\[\[|test)[^\n]{0,240}\bDarwin\b"),
        "missing executable Darwin OS guard")
require(
    1,
    has(r"\bsw_vers\b[^\n]*-productVersion")
    and has(r"(?:-lt|<|-ge|>=)\s*14\b|\b14\s*(?:-gt|>|-le|<=)"),
        "missing macOS 14-or-newer version guard")
require(1, has(r"\buname\b[^\n]*-m") and has(r"(?:if|elif|case|\[\[|test)[^\n]{0,240}\barm64\b"),
        "missing Apple Silicon arm64 guard")
require(
    1,
    has(r"manifest\.json")
    and has(r"\bschemaVersion\b")
    and has(r"\bschemaVersion\b[^\n]{0,160}(?:==|!=|-eq|-ne|\beq\b|\bne\b)[^\n]{0,40}\b1\b")
    and has(r"\bplatform\b[^\n]{0,160}\bmacos\b")
    and has(r"\barchitecture\b[^\n]{0,160}\barm64\b")
    and fail_closed,
    "missing fail-closed schemaVersion=1/platform=macos/architecture=arm64 manifest guard",
)

# (2) Dry-run by default; only an explicit --apply may mutate the machine.
default_dry_run = has_any(
    r"\b(?:APPLY|DO_APPLY)\s*=\s*(?:0|false)\b",
    r"\bDRY_RUN\s*=\s*(?:1|true)\b",
    r"\bMODE\s*=\s*['\"]?dry[-_ ]?run\b",
)
explicit_apply = has(r"--apply\)") and has_any(
    r"--apply\).{0,240}\b(?:APPLY|DO_APPLY)\s*=\s*(?:1|true)\b",
    r"--apply\).{0,240}\bDRY_RUN\s*=\s*(?:0|false)\b",
    r"--apply\).{0,240}\bMODE\s*=\s*['\"]?apply\b",
)
apply_gate = has_any(
    r"\bif\b[^\n]{0,240}\b(?:APPLY|DO_APPLY|DRY_RUN|MODE)\b",
    r"\[\[[^\n]{0,240}\b(?:APPLY|DO_APPLY|DRY_RUN|MODE)\b[^\n]{0,240}\]\]",
)
require(2, default_dry_run, "missing non-mutating dry-run default")
require(2, explicit_apply, "missing explicit --apply mode transition")
require(2, apply_gate and has(r"dry[-_ ]?run|ドライラン"),
        "missing apply gate with a visible dry-run plan")

# (3) Integrity must fail on hash mismatch, missing/extra files, and unsafe paths.
require(
    3,
    has(r"\bsha-?256\b")
    and has_any(r"\bshasum\b[^\n]*-a\s+256", r"\bopenssl\b[^\n]*\bsha256\b", r"\bhashlib\.sha256\b"),
    "missing SHA-256 calculation for manifest files",
)
require(
    3,
    has_any(
        r"(?:sha|hash|digest|actual|computed|calculated)[^\n]{0,160}(?:==|!=|-eq|-ne)[^\n]{0,160}(?:sha|hash|digest|expected)",
        r"(?:expected|sha|hash|digest)[^\n]{0,160}(?:==|!=|-eq|-ne)[^\n]{0,160}(?:actual|computed|calculated|sha|hash|digest)",
    )
    and has(r"mismatch|不一致|hash[^\n]{0,80}(?:fail|error|invalid)")
    and fail_closed,
    "missing fail-closed comparison of calculated and manifest SHA-256 values",
)
require(
    3,
    has_any(r"!\s+-f\b", r"\b(?:is_file|exists)\s*\(")
    and has(r"missing|欠落|not[ -]?found")
    and fail_closed,
    "missing fail-closed check for manifest-listed files",
)
require(
    3,
    has_any(r"\bfind\b", r"\bos\.walk\b", r"\b(?:rglob|glob)\s*\(")
    and has(r"extra|unexpected|unlisted|not listed|未記載|余分|混入")
    and fail_closed,
    "missing fail-closed detection of files absent from the manifest",
)
require(
    3,
    has_any(r"\brealpath\b", r"\breadlink\b[^\n]*-f", r"\b(?:resolve|abspath|is_absolute)\s*\(", r"\bcase\b[^\n]{0,240}/\*")
    and has(r"traversal|outside[^\n]*kit|unsafe[ -]?path|キット外|パストラバーサル")
    and has(r"absolute[ -]?path|絶対パス|is_absolute")
    and fail_closed,
    "missing absolute-path/path-traversal containment guard",
)
reject(
    3,
    r"--skip-(?:hash|verify)|\bSKIP_(?:HASH|VERIFY)\b",
    "hash verification bypass is forbidden by CONTRACT.md",
)

# (4) Offline payload installation coverage: Python, VS Code, and Ollama.
require(
    4,
    has(r"runtime/python") and has(r"\.pkg\b") and has(r"\binstaller\b[^\n]*-pkg\b"),
    "missing installation path for the bundled Python .pkg",
)
require(
    4,
    has(r"runtime/vscode")
    and has(r"Visual Studio Code\.app")
    and has(r"\.(?:zip|dmg)\b")
    and has_any(r"\bditto\b", r"\bunzip\b", r"\bhdiutil\b"),
    "missing installation path for the bundled VS Code archive/image",
)
require(
    4,
    has(r"runtime/ollama")
    and has(r"Ollama\.app")
    and has(r"\.dmg\b")
    and has(r"\bhdiutil\b"),
    "missing installation path for the bundled Ollama DMG",
)

# (5) Ollama model cache and all three fixed configuration artifacts.
require(
    5,
    has(r"models/ollama") and has(r"\.ollama/(?:models|['\"]?\s*models)")
    and has_any(r"\bcp\b", r"\bditto\b", r"\brsync\b"),
    "missing Ollama model-cache placement into the user profile",
)
for config_path in (
    "config/chatLanguageModels.json",
    "config/settings.offline.json",
    "config/ollama-server.json",
):
    require(5, has(re.escape(config_path)), f"missing {config_path} placement")
require(
    5,
    has(r"Library/Application Support/Code/User") and has(r"\.ollama/(?:server\.json|['\"]?\s*server\.json)"),
    "missing macOS destinations for VS Code and Ollama configuration",
)
require(
    5,
    has_any(
        r"\b(?:install|place|copy)_configs?\b",
        r"\b(?:cp|ditto|rsync)\b[^\n]{0,240}(?:chatLanguageModels|settings\.offline|ollama-server)",
        r"(?:chatLanguageModels|settings\.offline|ollama-server)[^\n]{0,240}\b(?:cp|ditto|rsync)\b",
    ),
    "missing concrete placement operation for fixed configuration artifacts",
)

# (6) Existing equal content may be skipped; different settings must stop for manual merge.
require(
    6,
    has_any(r"\bcmp\b[^\n]*-s\b", r"\bdiff\b[^\n]*-q\b", r"\bfiles?_equal\b", r"existing[^\n]{0,160}\bsha-?256\b")
    and has(r"same|identical|unchanged|skip|同一|スキップ"),
    "missing idempotent same-content skip",
)
require(
    6,
    has(r"conflict|manual[ -]?merge|競合|手動マージ") and fail_closed,
    "missing fail-closed setting conflict with manual-merge guidance",
)

# (7) Installer and verification failures must retain a non-zero exit status.
strict_mode = has(r"(?:^|\n)\s*set\s+-[A-Za-z]*e[A-Za-z]*u[A-Za-z]*o\s+pipefail\b")
suppressed_failure = has(
    r"(?:installer|hdiutil|ditto|verify_endpoint\.py)[^\n]*(?:\|\|\s*true\b|;\s*true\b)"
)
explicit_status = has_any(
    r"\b(?:rc|status|exit_code)\s*=\s*\$\?[^\n]{0,240}\b(?:return|exit)\b[^\n]*(?:rc|status|exit_code)",
    r"\bexec\b[^\n]*(?:installer|verify_endpoint\.py)",
)
require(7, strict_mode, "missing set -euo pipefail exit propagation baseline")
require(7, not suppressed_failure, "installer or verifier exit status is suppressed")
require(
    7,
    strict_mode or explicit_status,
    "missing non-zero exit-code propagation for installers and endpoint verification",
)

# (8) verify_endpoint.py and Agent capability are mandatory, not best-effort.
require(
    8,
    has(r"tools/verify_endpoint\.py")
    and has_any(
        r"(?:!\s+-f|-f)[^\n]{0,240}verify_endpoint\.py",
        r"verify_endpoint\.py[^\n]{0,240}(?:is_file|exists)\s*\(",
    )
    and fail_closed,
    "missing required-file guard for tools/verify_endpoint.py",
)
require(
    8,
    has(r"verify_endpoint\.py") and has(r"--url\b") and has(r"--model\b"),
    "missing verify_endpoint.py invocation with endpoint and manifest model",
)
require(
    8,
    has(r"verify_endpoint\.py") and has(r"--expected-context\b"),
    "missing verify_endpoint.py invocation with manifest context length",
)
require(
    8,
    has(r"model[^\n]{0,80}supportsToolCalling|supportsToolCalling")
    and has(r"supportsToolCalling[^\n]{0,160}(?:==|!=|-eq|-ne|\beq\b|\bne\b)[^\n]{0,40}\btrue\b")
    and fail_closed,
    "missing fail-closed Agent gate requiring model.supportsToolCalling=true",
)
strict_agent_result = (
    has(r"\[\s*WARN\s*\]|結果:\s*すべて\s*OK")
    and has_any(r"\bgrep\b", r"\bcase\b", r"\bif\b")
    and fail_closed
)
require(
    8,
    strict_agent_result,
    "verify_endpoint Agent result is not enforced (warnings must not pass an Agent kit)",
)
require(
    8,
    has(r"pgrep\s+-x\s+Ollama") and has(r"pgrep\s+-x\s+ollama")
    and has(r"Ollama process is already running"),
    "existing Ollama process is not rejected before Apply",
)
require(
    8,
    has(r"nc\s+-z\s+-w\s+1\s+127[.]0[.]0[.]1\s+11434")
    and has(r"port 11434 is already in use"),
    "existing listener on the Ollama endpoint is not rejected before Apply",
)
context_set = re.search(r"launchctl\s+setenv\s+OLLAMA_CONTEXT_LENGTH", code, flags)
ollama_open = re.search(r"open\s+-a\s+Ollama", code, flags)
require(
    8,
    context_set is not None and ollama_open is not None and context_set.start() < ollama_open.start(),
    "launchctl context must be set before Ollama.app is opened",
)
require(
    8,
    has(r"open\s+-a\s+Ollama\s*\|\|\s*die"),
    "Ollama.app launch failure is not reported immediately",
)

failed_groups = {group: messages for group, messages in failures.items() if messages}
if failed_groups:
    total = sum(len(messages) for messages in failed_groups.values())
    print(f"RED: {total} static contract check(s) failed for {sut}", file=sys.stderr)
    for group, messages in failed_groups.items():
        print(f"  requirement ({group}):", file=sys.stderr)
        for message in messages:
            print(f"    - {message}", file=sys.stderr)
    raise SystemExit(1)

print(f"PASS: install-macos.sh satisfies all 8 static contract groups: {sut}")
PY
