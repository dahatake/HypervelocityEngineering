#!/usr/bin/env bash
# MT-01: CONTRACT.md に対する Prepare-macOS.sh の静的 RED 契約テスト。
# 対象スクリプトは実行も source もしないため、このテストからネットワーク通信は発生しない。

set -u
set -o pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$TEST_DIR/.." && pwd)"
SCRIPT_UNDER_TEST="$KIT_DIR/Prepare-macOS.sh"

if [[ ! -f "$SCRIPT_UNDER_TEST" ]]; then
    printf 'RED: Prepare-macOS.sh が存在しません: %s\n' "$SCRIPT_UNDER_TEST" >&2
    printf 'RED: MT-01 は将来の macOS 準備スクリプト実装まで失敗する契約テストです。\n' >&2
    exit 1
fi

# 全行コメントだけで契約語を満たす偽 GREEN を避ける。JSON heredoc 等の実データは残す。
SOURCE_CODE=''
while IFS= read -r line || [[ -n "$line" ]]; do
    trimmed="${line#"${line%%[![:space:]]*}"}"
    case "$trimmed" in
        ''|'#'*) continue ;;
    esac
    SOURCE_CODE="${SOURCE_CODE}${line}"$'\n'
done < "$SCRIPT_UNDER_TEST"

checks=0
failures=0

assert_match() {
    local label="$1"
    local pattern="$2"
    local status
    checks=$((checks + 1))
    LC_ALL=C grep -E -q -e "$pattern" <<< "$SOURCE_CODE"
    status=$?
    if (( status == 0 )); then
        printf 'ok %d - %s\n' "$checks" "$label"
    else
        printf 'not ok %d - %s\n' "$checks" "$label" >&2
        if (( status > 1 )); then
            printf '  invalid ERE (grep exit %d): %s\n' "$status" "$pattern" >&2
        fi
        failures=$((failures + 1))
    fi
}

assert_not_match() {
    local label="$1"
    local pattern="$2"
    local status
    checks=$((checks + 1))
    LC_ALL=C grep -E -q -e "$pattern" <<< "$SOURCE_CODE"
    status=$?
    if (( status == 0 )); then
        printf 'not ok %d - %s\n' "$checks" "$label" >&2
        failures=$((failures + 1))
    elif (( status == 1 )); then
        printf 'ok %d - %s\n' "$checks" "$label"
    else
        printf 'not ok %d - %s\n' "$checks" "$label" >&2
        printf '  invalid ERE (grep exit %d): %s\n' "$status" "$pattern" >&2
        failures=$((failures + 1))
    fi
}

printf '# MT-01 Prepare-macOS.sh static contract checks\n'

# (1) macOS 14+ / Apple Silicon arm64 guard
assert_match 'OS guard reads uname -s' 'uname[[:space:]]+-s'
assert_match 'OS guard condition requires Darwin' '(if|elif|case|\[\[|test).*Darwin'
assert_match 'OS guard reads macOS ProductVersion' 'sw_vers[[:space:]]+-productVersion'
assert_match 'OS guard enforces a major version boundary at 14' '(-lt|<|-ge|>=)[[:space:]]*14|14[[:space:]]*(-gt|>|-le|<=)'
assert_match 'architecture guard reads uname -m' 'uname[[:space:]]+-m'
assert_match 'architecture guard condition requires arm64' '(if|elif|case|\[\[|test).*arm64'

# (2) Destination must be absent or empty before collection starts.
assert_match 'Destination is an explicit input' '--[Dd]estination|DESTINATION|Destination'
assert_match 'Destination existence is checked' '\[[^]]*-[[:space:]]*[ed][[:space:]]+[^]]+\]|test[[:space:]]+-[ed][[:space:]]+'
assert_match 'Destination non-empty state is detected' 'ls[[:space:]]+-A|find[[:space:]].*-mindepth[[:space:]]+1|dotglob|nullglob'
assert_match 'non-empty Destination has a rejection diagnostic' '[Nn]on-empty|[Nn]ot empty|must be empty|空でな|空では'

# (3) Every CONTRACT.md mandatory macOS component has a concrete kit path.
assert_match 'Python runtime is collected' 'runtime/python'
assert_match 'Python installer is a pkg' '[Pp]ython.*[.]pkg|[.]pkg.*[Pp]ython'
assert_match 'VS Code runtime is collected' 'runtime/vscode'
assert_match 'VS Code artifact is zip or dmg' '([Vv][Ss][[:space:]]*[Cc]ode|[Vv][Ss][Cc]ode).*[.](zip|dmg)|[.](zip|dmg).*([Vv][Ss][[:space:]]*[Cc]ode|[Vv][Ss][Cc]ode)'
assert_match 'Ollama runtime is collected' 'runtime/ollama'
assert_match 'Ollama installer is a dmg' '[Oo]llama.*[.]dmg|[.]dmg.*[Oo]llama'
assert_match 'Ollama model cache is collected' 'models/ollama'
assert_match 'BYOK model config is collected' 'config/chatLanguageModels[.]json'
assert_match 'offline VS Code config is collected' 'config/settings[.]offline[.]json'
assert_match 'Ollama local-only config is collected' 'config/ollama-server[.]json'
assert_match 'offline installer entry is collected' 'install-macos[.]sh'
assert_match 'endpoint verifier is collected' 'tools/verify_endpoint[.]py'
assert_match 'macOS guide is collected' 'docs/MACOS[.]md'
assert_match 'generated macOS guide checks VS Code by app-bundle path' '/Applications/Visual Studio Code[.]app/Contents/Resources/app/bin/code'
assert_match 'generated macOS guide checks Ollama by app-bundle path' '/Applications/Ollama[.]app/Contents/Resources/ollama'
assert_match 'generated macOS guide derives Python path from collected version' 'python_series.*python_version_parts|Versions/\{python_series\}'

# (4) Contract defaults are fixed unless explicitly overridden by the caller.
assert_match 'default model is qwen3:8b' '([Mm][Oo][Dd][Ee][Ll]|MODEL).*qwen3:8b'
assert_match 'default context length is 8192' '(contextLength|CONTEXT_LENGTH|context_length).*8192'
assert_match 'context length reserves input and output tokens' 'CONTEXT_LENGTH.*-ge[[:space:]]+2|CONTEXT_LENGTH.*>=[[:space:]]*2'
assert_match 'BYOK config is generated from the selected model' 'chatLanguageModels[.]json.*MODEL_NAME|MODEL_NAME.*chatLanguageModels[.]json'
assert_match 'BYOK config is generated from the selected context length' 'chatLanguageModels[.]json.*CONTEXT_LENGTH|CONTEXT_LENGTH.*chatLanguageModels[.]json'
assert_not_match 'fixed config source directory is not copied' 'CONFIG_SOURCE_DIR'

# (5) manifest.json contains every required top-level, model, component, and file field.
assert_match 'manifest.json is generated' 'manifest[.]json'
assert_match 'manifest schemaVersion is 1' '"schemaVersion"[[:space:]]*:[[:space:]]*1([^0-9]|$)'
assert_match 'manifest has createdAt' '"createdAt"[[:space:]]*:'
assert_match 'manifest createdAt is generated in UTC' 'date[[:space:]]+-u.*%Y-%m-%dT%H:%M:%SZ'
assert_match 'manifest platform is macos' '"platform"[[:space:]]*:[[:space:]]*"macos"'
assert_match 'manifest architecture is arm64' '"architecture"[[:space:]]*:[[:space:]]*"arm64"'
assert_match 'manifest has model object' '"model"[[:space:]]*:'
assert_match 'manifest model has name' '"name"[[:space:]]*:'
assert_match 'manifest model has digest' '"digest"[[:space:]]*:'
assert_match 'manifest model has supportsToolCalling' '"supportsToolCalling"[[:space:]]*:'
assert_match 'manifest has contextLength' '"contextLength"[[:space:]]*:'
assert_match 'manifest has components' '"components"[[:space:]]*:'
assert_match 'component entries identify required status' '"required"[[:space:]]*:'
assert_match 'component entries record actual version' '"version"[[:space:]]*:'
assert_match 'component entries use kit-relative path' '"path"[[:space:]]*:'
assert_match 'manifest has files' '"files"[[:space:]]*:'
assert_match 'file entries record byte count' '"bytes"[[:space:]]*:'
assert_match 'file entries record SHA-256' '"sha256"[[:space:]]*:'
assert_match 'file hashing uses macOS shasum SHA-256' 'shasum[[:space:]]+-a[[:space:]]+256'

# (6) Required acquisition and validation failures must stop before success/manifest completion.
assert_match 'strict error mode enables errexit' 'set[[:space:]]+-.*e'
assert_match 'strict error mode enables nounset' 'set[[:space:]]+-.*u'
assert_match 'strict error mode enables pipefail' 'set[[:space:]]+-o[[:space:]]+pipefail|set[[:space:]]+-.*o[[:space:]]+pipefail'
assert_match 'downloads use curl fail mode' 'curl.*(--fail|-[[:alpha:]]*f[[:alpha:]]*)'
assert_match 'required artifacts are checked as non-empty files' '\[[^]]*-[[:space:]]*s[[:space:]]+[^]]+\]|test[[:space:]]+-s[[:space:]]+'
assert_match 'fatal path returns a non-zero status' 'exit[[:space:]]+[1-9][0-9]*|return[[:space:]]+[1-9][0-9]*'
assert_match 'prepared model is verified with ollama list' 'ollama[[:space:]]+list'
assert_match 'Agent verification receives expected context' '--expected-context[[:space:]]+"?\$CONTEXT_LENGTH"?'
assert_match 'dedicated Ollama validation port is used' '127[.]0[.]0[.]1:11435'
assert_match 'dedicated Ollama server receives selected context' 'OLLAMA_CONTEXT_LENGTH="?\$CONTEXT_LENGTH"?.*serve'
assert_match 'any listener on the validation port is rejected' 'nc[[:space:]]+-z[[:space:]]+-w[[:space:]]+1[[:space:]]+127[.]0[.]0[.]1[[:space:]]+11435'
assert_match 'dedicated Ollama startup failures expose log tail' 'tail[[:space:]]+-n[[:space:]]+30[[:space:]]+"?\$OLLAMA_SERVE_LOG"?'
assert_not_match 'required failures are not erased with || true' '[|][|][[:space:]]*true([[:space:]]|$)'
assert_not_match 'strict failure handling is not disabled with set +e' 'set[[:space:]]+[+]e'

# (7) Foundry Local remains opt-in; selecting it makes installer and model mandatory.
# These are static-only assertions: Prepare-macOS.sh is never executed by this test.
assert_match 'Foundry Local has an explicit opt-in flag' '--include-foundry(-local)?|INCLUDE_FOUNDRY(_LOCAL)?'
assert_match 'Foundry Local defaults to disabled' "INCLUDE_FOUNDRY(_LOCAL)?[[:space:]]*=[[:space:]]*['\"]?(0|false)['\"]?([[:space:]]|$)"
assert_match 'Foundry Local collection is conditional' '(if|elif).*INCLUDE_FOUNDRY(_LOCAL)?|case.*INCLUDE_FOUNDRY(_LOCAL)?'
assert_match 'optional Foundry runtime has the contract path' 'runtime/foundry-local'
assert_match 'optional Foundry model has the contract path' 'models/foundry-local'
assert_match 'selected Foundry artifacts are required, not warning-only' '(require|assert|verify|\[[^]]*-[[:space:]]*s).*([Ff]oundry|FOUNDRY)|([Ff]oundry|FOUNDRY).*(require|assert|verify|-[[:space:]]*s)'

if (( failures > 0 )); then
    printf 'RED: %d/%d static contract checks failed for %s\n' \
        "$failures" "$checks" "$SCRIPT_UNDER_TEST" >&2
    exit 1
fi

printf 'GREEN: all %d static contract checks passed for %s\n' \
    "$checks" "$SCRIPT_UNDER_TEST"
