#!/usr/bin/env bash

# macOS 14+ / Apple Silicon のオンライン準備機でオフラインキットを作る。
# Bash 3.2 と macOS 標準コマンドだけを前提にし、manifest.json は最後に生成する。

set -euo pipefail

PYTHON_VERSION='3.14.7'
PYTHON_URL='https://www.python.org/ftp/python/3.14.7/python-3.14.7-macos11.pkg'
PYTHON_EXPECTED_SHA256='70c5239ad2d62925d2947e46921d0ddd3d35be3d2f0a2d50db33da507dbcb419'
VSCODE_URL='https://update.code.visualstudio.com/latest/darwin-arm64/stable'
OLLAMA_URL='https://ollama.com/download/Ollama.dmg'

PYTHON_ARTIFACT_RELATIVE='runtime/python/Python-Universal2.pkg'
VSCODE_ARTIFACT_RELATIVE='runtime/vscode/VSCode-darwin-arm64.zip'
OLLAMA_ARTIFACT_RELATIVE='runtime/ollama/Ollama.dmg'

DESTINATION=''
MODEL='qwen3:8b'
CONTEXT_LENGTH='8192'
INCLUDE_FOUNDRY_LOCAL=0
FOUNDRY_LOCAL_URL=''
FOUNDRY_MODEL_SOURCE=''
FOUNDRY_ARTIFACT_NAME=''
FOUNDRY_ARTIFACT_RELATIVE=''
FOUNDRY_VERSION=''

TEMP_ROOT=''
OLLAMA_MOUNT_POINT=''
OLLAMA_SERVE_PID=''
OLLAMA_SERVE_LOG=''
OLLAMA_VALIDATION_HOST='127.0.0.1:11435'
OLLAMA_VALIDATION_URL='http://127.0.0.1:11435'

usage() {
    cat <<'USAGE'
Usage:
  Prepare-macOS.sh --destination PATH [options]

Options:
  --destination PATH             Required. Must be absent or an empty directory.
  --model NAME                   Ollama model returned by `ollama list`.
                                 Default: qwen3:8b
    --context-length TOKENS        Integer 2 or greater. Default: 8192
  --include-foundry-local        Include Foundry Local runtime and model cache.
  --foundry-local-url URL        Required with --include-foundry-local.
                                 Use the exact macOS arm64 .pkg/.zip release asset
                                 selected from https://aka.ms/foundry-local-installer.
  --foundry-model-source PATH    Required with --include-foundry-local. This must
                                 be a non-empty, already downloaded model cache.
  -h, --help                     Show this help.

Required repository collection sources:
  install-macos.sh
  ../verify_endpoint.py

Prepare-macOS.sh never synthesizes a missing installer or verifier.
USAGE
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "$OLLAMA_SERVE_PID" ]]; then
        kill "$OLLAMA_SERVE_PID" >/dev/null 2>&1 || :
        wait "$OLLAMA_SERVE_PID" >/dev/null 2>&1 || :
        OLLAMA_SERVE_PID=''
    fi
    if [[ -n "$OLLAMA_MOUNT_POINT" && -d "$OLLAMA_MOUNT_POINT" ]]; then
        hdiutil detach "$OLLAMA_MOUNT_POINT" >/dev/null 2>&1 || :
    fi
    if [[ -n "$TEMP_ROOT" && -d "$TEMP_ROOT" ]]; then
        rm -rf "$TEMP_ROOT" || :
    fi
}

on_signal() {
    trap - EXIT
    cleanup
    exit 130
}

trap cleanup EXIT
trap on_signal HUP INT TERM

require_option_value() {
    local option_name="$1"
    local option_value="${2-}"
    [[ -n "$option_value" ]] || die "$option_name requires a non-empty value"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --destination)
            [[ $# -ge 2 ]] || die '--destination requires a value'
            require_option_value '--destination' "$2"
            DESTINATION="$2"
            shift 2
            ;;
        --destination=*)
            DESTINATION="${1#*=}"
            require_option_value '--destination' "$DESTINATION"
            shift
            ;;
        --model)
            [[ $# -ge 2 ]] || die '--model requires a value'
            require_option_value '--model' "$2"
            MODEL="$2"
            shift 2
            ;;
        --model=*)
            MODEL="${1#*=}"
            require_option_value '--model' "$MODEL"
            shift
            ;;
        --context-length)
            [[ $# -ge 2 ]] || die '--context-length requires a value'
            require_option_value '--context-length' "$2"
            CONTEXT_LENGTH="$2"
            shift 2
            ;;
        --context-length=*)
            CONTEXT_LENGTH="${1#*=}"
            require_option_value '--context-length' "$CONTEXT_LENGTH"
            shift
            ;;
        --include-foundry-local)
            INCLUDE_FOUNDRY_LOCAL=1
            shift
            ;;
        --foundry-local-url)
            [[ $# -ge 2 ]] || die '--foundry-local-url requires a value'
            require_option_value '--foundry-local-url' "$2"
            FOUNDRY_LOCAL_URL="$2"
            shift 2
            ;;
        --foundry-local-url=*)
            FOUNDRY_LOCAL_URL="${1#*=}"
            require_option_value '--foundry-local-url' "$FOUNDRY_LOCAL_URL"
            shift
            ;;
        --foundry-model-source)
            [[ $# -ge 2 ]] || die '--foundry-model-source requires a value'
            require_option_value '--foundry-model-source' "$2"
            FOUNDRY_MODEL_SOURCE="$2"
            shift 2
            ;;
        --foundry-model-source=*)
            FOUNDRY_MODEL_SOURCE="${1#*=}"
            require_option_value '--foundry-model-source' "$FOUNDRY_MODEL_SOURCE"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            [[ $# -eq 0 ]] || die 'positional arguments are not supported'
            ;;
        -*|*)
            die "unknown argument: $1"
            ;;
    esac
done

[[ -n "$DESTINATION" ]] || die '--destination is required and must be non-empty'

case "$CONTEXT_LENGTH" in
    ''|*[!0-9]*|0*) die '--context-length must be a canonical integer of 2 or greater' ;;
esac
[[ ${#CONTEXT_LENGTH} -le 9 ]] || die '--context-length is too large'
[[ "$CONTEXT_LENGTH" -ge 2 ]] || die '--context-length must reserve at least one input and one output token'

case "$MODEL" in
    ''|*[!A-Za-z0-9._:/@-]*) die '--model contains unsupported characters' ;;
    /*|*'..'*|*/*/*) die '--model must not contain an absolute path, traversal, or registry host' ;;
esac

if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    [[ -n "$FOUNDRY_LOCAL_URL" ]] || die '--foundry-local-url is required with --include-foundry-local'
    [[ -n "$FOUNDRY_MODEL_SOURCE" ]] || die '--foundry-model-source is required with --include-foundry-local'
    case "$FOUNDRY_LOCAL_URL" in
        *'?'*|*'#'*|*'@'*)
            die '--foundry-local-url must not contain credentials, a query, or a fragment'
            ;;
        https://github.com/microsoft/Foundry-Local/releases/download/*|\
        https://github.com/microsoft/foundry-local/releases/download/*)
            ;;
        *)
            die '--foundry-local-url must be an official microsoft/Foundry-Local GitHub release asset'
            ;;
    esac
    case "$FOUNDRY_LOCAL_URL" in
        https://github.com/microsoft/Foundry-Local/releases/download/*)
            FOUNDRY_RELEASE_ASSET_PATH="${FOUNDRY_LOCAL_URL#https://github.com/microsoft/Foundry-Local/releases/download/}"
            ;;
        https://github.com/microsoft/foundry-local/releases/download/*)
            FOUNDRY_RELEASE_ASSET_PATH="${FOUNDRY_LOCAL_URL#https://github.com/microsoft/foundry-local/releases/download/}"
            ;;
    esac
    case "$FOUNDRY_RELEASE_ASSET_PATH" in
        */*) ;;
        *) die '--foundry-local-url must contain one release tag and one asset name' ;;
    esac
    FOUNDRY_RELEASE_TAG="${FOUNDRY_RELEASE_ASSET_PATH%%/*}"
    FOUNDRY_ARTIFACT_NAME="${FOUNDRY_RELEASE_ASSET_PATH#*/}"
    case "$FOUNDRY_RELEASE_TAG" in
        ''|.|..|*[!A-Za-z0-9._+-]*) die '--foundry-local-url contains an unsafe release tag' ;;
    esac
    case "$FOUNDRY_ARTIFACT_NAME" in
        ''|*/*|.|..|*[!A-Za-z0-9._+-]*) die '--foundry-local-url contains an unsafe asset name' ;;
    esac
    case "$FOUNDRY_ARTIFACT_NAME" in
        *.pkg)
            FOUNDRY_ARTIFACT_RELATIVE='runtime/foundry-local/FoundryLocal.pkg'
            ;;
        *.zip)
            FOUNDRY_ARTIFACT_RELATIVE='runtime/foundry-local/FoundryLocal.zip'
            ;;
        *)
            die '--foundry-local-url must identify a .pkg or .zip release asset'
            ;;
    esac
else
    [[ -z "$FOUNDRY_LOCAL_URL" && -z "$FOUNDRY_MODEL_SOURCE" ]] || \
        die 'Foundry Local inputs require --include-foundry-local'
fi

OS_NAME="$(uname -s)"
if [[ "$OS_NAME" != 'Darwin' ]]; then
    die "unsupported operating system: expected Darwin, got $OS_NAME"
fi

MACOS_VERSION="$(sw_vers -productVersion)"
MACOS_MAJOR="${MACOS_VERSION%%.*}"
case "$MACOS_MAJOR" in
    ''|*[!0-9]*) die 'sw_vers returned an invalid macOS ProductVersion' ;;
esac
if [[ "$MACOS_MAJOR" -lt 14 ]]; then
    die "unsupported macOS version: $MACOS_VERSION; macOS 14 or newer is required"
fi

MACHINE_ARCH="$(uname -m)"
if [[ "$MACHINE_ARCH" != 'arm64' ]]; then
    die "unsupported architecture: expected arm64, got $MACHINE_ARCH"
fi

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command is unavailable: $1"
}

for required_command in \
    awk bash cat chmod curl date dirname ditto file find grep head hdiutil ls mkdir \
    installer kill mktemp mv nc plutil pkgutil rm sed shasum sleep sort sudo tail tr wc
do
    require_command "$required_command"
done

if [[ -e "$DESTINATION" ]]; then
    [[ -d "$DESTINATION" ]] || die 'Destination exists but is not a directory'
    [[ ! -L "$DESTINATION" ]] || die 'Destination must not be a symbolic link'
    if [[ -n "$(ls -A "$DESTINATION")" ]]; then
        die 'non-empty Destination is forbidden; Destination must be absent or empty'
    fi
fi

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
INSTALL_SOURCE="$SCRIPT_DIR/install-macos.sh"
VERIFY_SOURCE="$SCRIPT_DIR/../verify_endpoint.py"

require_source_file() {
    local label="$1"
    local path="$2"
    [[ -f "$path" && ! -L "$path" && -s "$path" ]] || \
        die "required collection source is missing, empty, or unsafe ($label)"
}

require_source_directory() {
    local label="$1"
    local path="$2"
    [[ -d "$path" && ! -L "$path" ]] || \
        die "required collection source directory is missing or unsafe ($label)"
    if ! find "$path" -type f -print -quit | grep -q .; then
        die "required collection source directory has no files ($label)"
    fi
    if find "$path" -type l -print -quit | grep -q .; then
        die "symbolic links are forbidden in collection source directory ($label)"
    fi
}

require_source_file 'install-macos.sh' "$INSTALL_SOURCE"
require_source_file 'tools/verify_endpoint.py' "$VERIFY_SOURCE"

bash -n "$INSTALL_SOURCE" || die 'required install-macos.sh has invalid Bash syntax'

if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    require_source_directory 'Foundry Local downloaded model cache' "$FOUNDRY_MODEL_SOURCE"
    FOUNDRY_MODEL_SOURCE="$(CDPATH='' cd -- "$FOUNDRY_MODEL_SOURCE" && pwd -P)"
fi

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/prepare-macos.XXXXXX")"
[[ -d "$TEMP_ROOT" ]] || die 'failed to create a temporary directory'

download_required() {
    local label="$1"
    local url="$2"
    local destination_path="$3"
    local partial_path="${destination_path}.part"

    case "$url" in
        https://*) ;;
        *) die "required download URL is not HTTPS ($label)" ;;
    esac

    rm -f "$partial_path"
    if ! curl --fail --location --show-error --silent \
        --proto '=https' --proto-redir '=https' \
        --retry 3 --connect-timeout 30 --max-time 3600 \
        --output "$partial_path" "$url"
    then
        die "required download failed ($label)"
    fi
    [[ -s "$partial_path" ]] || die "required download is empty ($label)"
    mv "$partial_path" "$destination_path"
    [[ -s "$destination_path" ]] || die "required artifact is empty ($label)"
}

file_sha256() {
    shasum -a 256 "$1" | awk '{ print $1 }'
}

validate_metadata_value() {
    local label="$1"
    local value="$2"
    [[ -n "$value" ]] || die "empty metadata value ($label)"
    case "$value" in
        *[!A-Za-z0-9._+-]*) die "unsafe metadata value ($label)" ;;
    esac
}

PYTHON_ARTIFACT_TEMP="$TEMP_ROOT/Python-Universal2.pkg"
VSCODE_ARTIFACT_TEMP="$TEMP_ROOT/VSCode-darwin-arm64.zip"
OLLAMA_ARTIFACT_TEMP="$TEMP_ROOT/Ollama.dmg"
FOUNDRY_ARTIFACT_TEMP=''

# Acquire every required runtime before changing the preparation machine.
download_required 'Python Universal2 .pkg' "$PYTHON_URL" "$PYTHON_ARTIFACT_TEMP"
download_required 'VS Code Apple Silicon .zip' "$VSCODE_URL" "$VSCODE_ARTIFACT_TEMP"
download_required 'Ollama macOS .dmg' "$OLLAMA_URL" "$OLLAMA_ARTIFACT_TEMP"
if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    case "$FOUNDRY_ARTIFACT_NAME" in
        *.pkg) FOUNDRY_ARTIFACT_TEMP="$TEMP_ROOT/FoundryLocal.pkg" ;;
        *.zip) FOUNDRY_ARTIFACT_TEMP="$TEMP_ROOT/FoundryLocal.zip" ;;
    esac
    download_required 'Foundry Local macOS arm64 pkg/zip' \
        "$FOUNDRY_LOCAL_URL" "$FOUNDRY_ARTIFACT_TEMP"
fi

PYTHON_ACTUAL_SHA256="$(file_sha256 "$PYTHON_ARTIFACT_TEMP")"
[[ "$PYTHON_ACTUAL_SHA256" == "$PYTHON_EXPECTED_SHA256" ]] || \
    die 'Python Universal2 .pkg does not match the official release SHA-256'

PYTHON_EXPANDED="$TEMP_ROOT/python-package"
if ! pkgutil --expand-full "$PYTHON_ARTIFACT_TEMP" "$PYTHON_EXPANDED" >/dev/null; then
    die 'Python artifact is not a readable macOS .pkg'
fi
PYTHON_METADATA="$TEMP_ROOT/python-package-metadata"
find "$PYTHON_EXPANDED" -type f \( -name Distribution -o -name PackageInfo \) \
    -exec cat {} \; > "$PYTHON_METADATA"
grep -Fq "version=\"$PYTHON_VERSION\"" "$PYTHON_METADATA" || \
    die 'Python .pkg metadata does not contain the expected actual version'
grep -Fq 'arm64' "$PYTHON_METADATA" || die 'Python .pkg metadata does not include arm64'
grep -Fq 'x86_64' "$PYTHON_METADATA" || die 'Python .pkg is not a Universal2 artifact'

VSCODE_EXPANDED="$TEMP_ROOT/vscode"
mkdir -p "$VSCODE_EXPANDED"
if ! ditto -x -k "$VSCODE_ARTIFACT_TEMP" "$VSCODE_EXPANDED"; then
    die 'VS Code artifact is not a readable zip'
fi
VSCODE_APP="$VSCODE_EXPANDED/Visual Studio Code.app"
VSCODE_PLIST="$VSCODE_APP/Contents/Info.plist"
VSCODE_BINARY="$VSCODE_APP/Contents/MacOS/Electron"
require_source_file 'VS Code Info.plist' "$VSCODE_PLIST"
require_source_file 'VS Code Apple Silicon binary' "$VSCODE_BINARY"
file "$VSCODE_BINARY" | grep -q 'arm64' || die 'VS Code artifact does not contain an arm64 binary'
if ! VSCODE_VERSION="$(plutil -extract CFBundleShortVersionString raw -o - "$VSCODE_PLIST")"; then
    die 'unable to read the actual VS Code version'
fi
validate_metadata_value 'VS Code version' "$VSCODE_VERSION"

OLLAMA_MOUNT_POINT="$TEMP_ROOT/ollama-mount"
mkdir -p "$OLLAMA_MOUNT_POINT"
if ! hdiutil attach "$OLLAMA_ARTIFACT_TEMP" \
    -nobrowse -readonly -mountpoint "$OLLAMA_MOUNT_POINT" >/dev/null
then
    die 'Ollama artifact is not a readable dmg'
fi
OLLAMA_APP="$OLLAMA_MOUNT_POINT/Ollama.app"
OLLAMA_PLIST="$OLLAMA_APP/Contents/Info.plist"
OLLAMA_BINARY="$OLLAMA_APP/Contents/Resources/ollama"
require_source_file 'Ollama Info.plist' "$OLLAMA_PLIST"
require_source_file 'Ollama arm64 binary' "$OLLAMA_BINARY"
file "$OLLAMA_BINARY" | grep -q 'arm64' || die 'Ollama dmg does not contain an arm64 binary'
if ! OLLAMA_ARTIFACT_VERSION="$(plutil -extract CFBundleShortVersionString raw -o - "$OLLAMA_PLIST")"; then
    die 'unable to read the actual Ollama artifact version'
fi
validate_metadata_value 'Ollama artifact version' "$OLLAMA_ARTIFACT_VERSION"

if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    case "$FOUNDRY_ARTIFACT_NAME" in
        *.pkg)
            FOUNDRY_EXPANDED="$TEMP_ROOT/foundry-package"
            if ! pkgutil --expand-full "$FOUNDRY_ARTIFACT_TEMP" \
                "$FOUNDRY_EXPANDED" >/dev/null
            then
                die 'Foundry Local artifact is not a readable macOS pkg'
            fi
            FOUNDRY_VERSION_CANDIDATES="$TEMP_ROOT/foundry-package-versions"
            find "$FOUNDRY_EXPANDED" -type f -name PackageInfo \
                -exec grep -i 'identifier="[^"]*foundry[^"]*"' {} \; | \
                sed -nE 's/.*[[:space:]]version="([^"]+)".*/\1/p' | \
                LC_ALL=C sort -u > "$FOUNDRY_VERSION_CANDIDATES"
            FOUNDRY_VERSION_COUNT="$(wc -l < "$FOUNDRY_VERSION_CANDIDATES" | tr -d '[:space:]')"
            [[ "$FOUNDRY_VERSION_COUNT" -eq 1 ]] || \
                die 'Foundry Local pkg metadata must identify exactly one actual version'
            FOUNDRY_VERSION="$(cat "$FOUNDRY_VERSION_CANDIDATES")"
            FOUNDRY_BINARY="$(find "$FOUNDRY_EXPANDED" -type f -name foundry -print -quit)"
            require_source_file 'Foundry Local arm64 binary' "$FOUNDRY_BINARY"
            file "$FOUNDRY_BINARY" | grep -q 'arm64' || \
                die 'Foundry Local pkg does not contain an arm64 binary'
            ;;
        *.zip)
            FOUNDRY_EXPANDED="$TEMP_ROOT/foundry-zip"
            mkdir -p "$FOUNDRY_EXPANDED"
            if ! ditto -x -k "$FOUNDRY_ARTIFACT_TEMP" "$FOUNDRY_EXPANDED"; then
                die 'Foundry Local artifact is not a readable zip'
            fi
            FOUNDRY_BINARY="$(find "$FOUNDRY_EXPANDED" -type f -name foundry -perm -111 -print -quit)"
            require_source_file 'Foundry Local arm64 binary' "$FOUNDRY_BINARY"
            file "$FOUNDRY_BINARY" | grep -q 'arm64' || \
                die 'Foundry Local zip does not contain an arm64 binary'
            if ! FOUNDRY_BINARY_VERSION_OUTPUT="$("$FOUNDRY_BINARY" --version 2>&1)"; then
                die 'unable to run the Foundry Local CLI from the downloaded zip'
            fi
            FOUNDRY_VERSION="$(printf '%s\n' "$FOUNDRY_BINARY_VERSION_OUTPUT" | \
                tr '[:space:]' '\n' | \
                sed -nE 's/^[vV]?([0-9]+\.[0-9]+(\.[0-9]+)?([-+][0-9A-Za-z.-]+)?)$/\1/p' | \
                head -n 1)"
            ;;
    esac
    validate_metadata_value 'Foundry Local version' "$FOUNDRY_VERSION"
fi

find_python_310() {
    local candidate_name=''
    local candidate_path=''

    for candidate_name in \
        python3 python3.14 python3.13 python3.12 python3.11 python3.10 \
        /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.10/bin/python3
    do
        case "$candidate_name" in
            /*) candidate_path="$candidate_name" ;;
            *) candidate_path="$(command -v "$candidate_name" 2>/dev/null || :)" ;;
        esac
        if [[ -n "$candidate_path" && -x "$candidate_path" ]] && \
            "$candidate_path" -c \
                'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
                >/dev/null 2>&1
        then
            printf '%s\n' "$candidate_path"
            return 0
        fi
    done
    return 1
}

PYTHON_COMMAND=''
if ! PYTHON_COMMAND="$(find_python_310)"; then
    sudo installer -pkg "$PYTHON_ARTIFACT_TEMP" -target /
    hash -r
    if ! PYTHON_COMMAND="$(find_python_310)"; then
        die 'Python 3.10 or newer is unavailable after installing the verified package'
    fi
fi

find_ollama_command() {
    local candidate_path=''

    candidate_path="$(command -v ollama 2>/dev/null || :)"
    if [[ -n "$candidate_path" && -x "$candidate_path" ]] && \
        OLLAMA_HOST='127.0.0.1:11434' "$candidate_path" --version >/dev/null 2>&1
    then
        printf '%s\n' "$candidate_path"
        return 0
    fi
    candidate_path='/Applications/Ollama.app/Contents/Resources/ollama'
    if [[ -x "$candidate_path" ]] && \
        OLLAMA_HOST='127.0.0.1:11434' "$candidate_path" --version >/dev/null 2>&1
    then
        printf '%s\n' "$candidate_path"
        return 0
    fi
    return 1
}

OLLAMA_COMMAND=''
if ! OLLAMA_COMMAND="$(find_ollama_command)"; then
    [[ ! -e '/Applications/Ollama.app' ]] || \
        die 'an unusable /Applications/Ollama.app already exists; refusing to replace it'
    sudo ditto "$OLLAMA_APP" '/Applications/Ollama.app'
    OLLAMA_COMMAND='/Applications/Ollama.app/Contents/Resources/ollama'
    [[ -x "$OLLAMA_COMMAND" ]] || die 'verified Ollama app installation did not provide its CLI'
    OLLAMA_HOST='127.0.0.1:11434' "$OLLAMA_COMMAND" --version >/dev/null 2>&1 || \
        die 'installed Ollama CLI failed its version check'
fi

run_ollama() {
    OLLAMA_HOST="$OLLAMA_VALIDATION_HOST" "$OLLAMA_COMMAND" "$@"
}

ollama_daemon_responds() {
    curl --fail --silent --show-error --noproxy '*' \
        --connect-timeout 2 --max-time 5 \
        "$OLLAMA_VALIDATION_URL/api/tags" >/dev/null 2>&1
}

report_ollama_serve_log() {
    if [[ -n "$OLLAMA_SERVE_LOG" && -s "$OLLAMA_SERVE_LOG" ]]; then
        printf '%s\n' '--- dedicated Ollama server log: last 30 lines ---' >&2
        tail -n 30 "$OLLAMA_SERVE_LOG" >&2
    fi
}

if nc -z -w 1 127.0.0.1 11435 >/dev/null 2>&1; then
    die 'Ollama validation port 11435 is already in use'
fi
OLLAMA_SERVE_LOG="$TEMP_ROOT/ollama-serve.log"
OLLAMA_HOST="$OLLAMA_VALIDATION_HOST" OLLAMA_CONTEXT_LENGTH="$CONTEXT_LENGTH" "$OLLAMA_COMMAND" serve \
    > "$OLLAMA_SERVE_LOG" 2>&1 &
OLLAMA_SERVE_PID=$!
OLLAMA_START_ATTEMPTS=0
while ! ollama_daemon_responds; do
    OLLAMA_START_ATTEMPTS=$((OLLAMA_START_ATTEMPTS + 1))
    if ! kill -0 "$OLLAMA_SERVE_PID" >/dev/null 2>&1; then
        if wait "$OLLAMA_SERVE_PID"; then
            OLLAMA_EXIT_STATUS=0
        else
            OLLAMA_EXIT_STATUS=$?
        fi
        OLLAMA_SERVE_PID=''
        report_ollama_serve_log
        die "dedicated ollama serve exited before readiness (exit $OLLAMA_EXIT_STATUS)"
    fi
    if [[ "$OLLAMA_START_ATTEMPTS" -ge 60 ]]; then
        report_ollama_serve_log
        die 'dedicated ollama serve did not become ready within 60 seconds'
    fi
    sleep 1
done

find_model_row() {
    awk -v wanted="$MODEL" '
        NR > 1 && ($1 == wanted || (index(wanted, ":") == 0 && $1 == wanted ":latest")) {
            print $1 "\t" $2
            found = 1
            exit
        }
        END { if (!found) exit 1 }
    '
}

OLLAMA_LIST_OUTPUT=''
if ! OLLAMA_LIST_OUTPUT="$(run_ollama list 2>&1)"; then
    printf '%s\n' "$OLLAMA_LIST_OUTPUT" >&2
    die 'ollama list failed on the preparation machine'
fi
MODEL_ROW=''
if ! MODEL_ROW="$(printf '%s\n' "$OLLAMA_LIST_OUTPUT" | find_model_row)"; then
    run_ollama pull "$MODEL" || die "ollama pull failed for required model: $MODEL"
    if ! OLLAMA_LIST_OUTPUT="$(run_ollama list 2>&1)"; then
        printf '%s\n' "$OLLAMA_LIST_OUTPUT" >&2
        die 'ollama list failed after pulling the required model'
    fi
    if ! MODEL_ROW="$(printf '%s\n' "$OLLAMA_LIST_OUTPUT" | find_model_row)"; then
        die "required model is absent after ollama pull: $MODEL"
    fi
fi

MODEL_NAME="${MODEL_ROW%%	*}"
MODEL_DIGEST="${MODEL_ROW#*	}"
MODEL_DIGEST="$(printf '%s' "$MODEL_DIGEST" | tr 'A-F' 'a-f')"
case "$MODEL_DIGEST" in
    sha256:*) MODEL_DIGEST="${MODEL_DIGEST#sha256:}" ;;
esac
case "$MODEL_DIGEST" in
    ''|*[!0-9a-f]*) die 'ollama list returned an invalid model digest' ;;
esac
[[ ${#MODEL_DIGEST} -ge 12 && ${#MODEL_DIGEST} -le 64 ]] || \
    die 'ollama list returned an invalid model digest length'

VERIFY_OUTPUT=''
if ! VERIFY_OUTPUT="$("$PYTHON_COMMAND" "$VERIFY_SOURCE" \
    --url "$OLLAMA_VALIDATION_URL" \
    --model "$MODEL_NAME" \
    --timeout 600 \
    --require-agent \
    --expected-context "$CONTEXT_LENGTH" 2>&1)"; then
    printf '%s\n' "$VERIFY_OUTPUT" >&2
    die 'verify_endpoint.py --require-agent rejected the Ollama model'
fi
printf '%s\n' "$VERIFY_OUTPUT"
case "$VERIFY_OUTPUT" in
    *'[ WARN ]'*) die 'verify_endpoint.py returned a warning; Agent kit creation is fail-closed' ;;
esac
printf '%s\n' "$VERIFY_OUTPUT" | grep -Fq '結果: すべて OK' || \
    die 'verify_endpoint.py did not report an unqualified Agent success'

OLLAMA_VERSION_OUTPUT=''
if ! OLLAMA_VERSION_OUTPUT="$(run_ollama --version 2>&1)"; then
    die 'ollama --version failed on the preparation machine'
fi
OLLAMA_PREP_VERSION="$(printf '%s\n' "$OLLAMA_VERSION_OUTPUT" | \
    tr '[:space:]' '\n' | \
    sed -nE 's/^[vV]?([0-9]+\.[0-9]+(\.[0-9]+)?([-+][0-9A-Za-z.-]+)?)$/\1/p' | \
    head -n 1)"
[[ -n "$OLLAMA_PREP_VERSION" ]] || die 'unable to determine preparation-machine Ollama version'

# Use exactly the cache configured for this process, or Ollama's documented user cache.
# Do not search alternate roots or fall back to copying the complete cache.
OLLAMA_MODELS_SOURCE=''
if [[ -n "${OLLAMA_MODELS:-}" ]]; then
    OLLAMA_MODELS_SOURCE="$OLLAMA_MODELS"
else
    [[ -n "${HOME:-}" ]] || die 'HOME is required to locate the Ollama model cache'
    OLLAMA_MODELS_SOURCE="$HOME/.ollama/models"
fi
require_source_directory 'Ollama model cache' "$OLLAMA_MODELS_SOURCE"
OLLAMA_MODELS_SOURCE="$(CDPATH='' cd -- "$OLLAMA_MODELS_SOURCE" && pwd -P)"

MODEL_MANIFEST=''
MODEL_MANIFEST_MATCHES=0
while IFS= read -r -d '' candidate_manifest; do
    candidate_digest="$(shasum -a 256 "$candidate_manifest" | awk '{ print $1 }')"
    if [[ "$candidate_digest" == "$MODEL_DIGEST"* ]]; then
        MODEL_MANIFEST="$candidate_manifest"
        MODEL_MANIFEST_MATCHES=$((MODEL_MANIFEST_MATCHES + 1))
    fi
done < <(find "$OLLAMA_MODELS_SOURCE/manifests" -type f -print0)

[[ "$MODEL_MANIFEST_MATCHES" -eq 1 ]] || \
    die 'unable to identify exactly one Ollama cache manifest for the selected model digest'
require_source_file 'selected Ollama model manifest' "$MODEL_MANIFEST"

BLOB_DIGESTS=''
if ! BLOB_DIGESTS="$("$PYTHON_COMMAND" - "$MODEL_MANIFEST" <<'PY'
import json
import re
import sys

with open(sys.argv[1], "r", encoding="utf-8") as stream:
    manifest = json.load(stream)

digests = []
config = manifest.get("config")
if isinstance(config, dict):
    digests.append(config.get("digest"))
for layer in manifest.get("layers", []):
    if isinstance(layer, dict):
        digests.append(layer.get("digest"))

seen = set()
for digest in digests:
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise SystemExit("invalid or missing sha256 blob digest in Ollama manifest")
    if digest not in seen:
        print(digest)
        seen.add(digest)
if not seen:
    raise SystemExit("Ollama manifest references no blobs")
PY
)"; then
    die 'failed to parse the selected Ollama cache manifest'
fi
[[ -n "$BLOB_DIGESTS" ]] || die 'selected Ollama model has no required cache blobs'

while IFS= read -r blob_digest; do
    [[ -n "$blob_digest" ]] || continue
    blob_hex="${blob_digest#sha256:}"
    require_source_file "Ollama blob $blob_digest" "$OLLAMA_MODELS_SOURCE/blobs/sha256-$blob_hex"
done <<EOF
$BLOB_DIGESTS
EOF

if [[ -e "$DESTINATION" ]]; then
    [[ -d "$DESTINATION" && ! -L "$DESTINATION" ]] || \
        die 'Destination changed to an unsafe path during preflight'
    if [[ -n "$(ls -A "$DESTINATION")" ]]; then
        die 'non-empty Destination appeared during preflight; collection is aborted'
    fi
fi

mkdir -p "$DESTINATION"
DESTINATION="$(CDPATH='' cd -- "$DESTINATION" && pwd -P)"

case "$DESTINATION/" in
    "$OLLAMA_MODELS_SOURCE/"*) die 'Destination must not be inside the Ollama cache' ;;
esac
if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    case "$DESTINATION/" in
        "$FOUNDRY_MODEL_SOURCE/"*) die 'Destination must not be inside the Foundry Local model source' ;;
    esac
fi

mkdir -p \
    "$DESTINATION/runtime/python" \
    "$DESTINATION/runtime/vscode" \
    "$DESTINATION/runtime/ollama" \
    "$DESTINATION/models/ollama" \
    "$DESTINATION/config" \
    "$DESTINATION/tools" \
    "$DESTINATION/docs"

copy_required_file() {
    local label="$1"
    local source_path="$2"
    local destination_path="$3"
    require_source_file "$label" "$source_path"
    ditto "$source_path" "$destination_path"
    [[ -s "$destination_path" ]] || die "required copy failed or is empty ($label)"
}

copy_required_file 'install-macos.sh' "$INSTALL_SOURCE" "$DESTINATION/install-macos.sh"
chmod 0755 "$DESTINATION/install-macos.sh"
copy_required_file 'tools/verify_endpoint.py' "$VERIFY_SOURCE" "$DESTINATION/tools/verify_endpoint.py"

"$PYTHON_COMMAND" - "$DESTINATION/config/chatLanguageModels.json" "$MODEL_NAME" "$CONTEXT_LENGTH" "$DESTINATION/config/settings.offline.json" "$DESTINATION/config/ollama-server.json" "$DESTINATION/docs/MACOS.md" "$PYTHON_VERSION" <<'PY'
import json
import sys
from pathlib import Path

chat_path = Path(sys.argv[1])
model = sys.argv[2]
context_length = int(sys.argv[3])
settings_path = Path(sys.argv[4])
ollama_path = Path(sys.argv[5])
guide_path = Path(sys.argv[6])
python_version = sys.argv[7]
python_version_parts = python_version.split(".")
if len(python_version_parts) < 2 or not all(part.isdigit() for part in python_version_parts[:2]):
    raise SystemExit("Python version must start with numeric major.minor components")
python_series = ".".join(python_version_parts[:2])

max_output_tokens = min(2048, max(1, context_length // 4))
max_input_tokens = context_length - max_output_tokens
if max_input_tokens < 1:
    raise SystemExit("context length must reserve at least one input token")

chat_models = [{
    "name": "Ollama (local)",
    "vendor": "customendpoint",
    "apiType": "chat-completions",
    "apiKey": "unused-but-required",
    "models": [{
        "id": model,
        "name": f"{model} (Ollama)",
        "url": "http://127.0.0.1:11434/v1/chat/completions",
        "toolCalling": True,
        "vision": False,
        "maxInputTokens": max_input_tokens,
        "maxOutputTokens": max_output_tokens,
    }],
}]
settings = {
    "extensions.autoUpdate": False,
    "extensions.autoCheckUpdates": False,
    "extensions.showRecommendationsOnlyOnDemand": True,
    "extensions.ignoreRecommendations": True,
    "chat.utilityModel": model,
    "chat.utilitySmallModel": model,
    "chat.byokUtilityModelDefault": "Main Agent Model",
    "inlineChat.defaultModel": model,
}

for path, value in (
    (chat_path, chat_models),
    (settings_path, settings),
    (ollama_path, {"disable_ollama_cloud": True}),
):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

guide_path.write_text(f"""# macOS オフライン導入

このディレクトリだけで検証と導入を行います。別途リポジトリを取得しません。

- 対象: macOS 14 以降 / Apple Silicon
- モデル: `{model}`
- コンテキスト長: `{context_length}`
- Agent/tool calling/context: 準備機で `verify_endpoint.py --require-agent --expected-context {context_length}` 成功済み

## ドライラン

Terminal で `./install-macos.sh` を実行します。既定では manifest、OS/CPU、SHA-256、
競合、導入予定だけを検証し、インストールや設定配置は行いません。

## 適用

ドライランに問題がなければ `./install-macos.sh --apply` を実行します。
必要な `sudo` 認証は macOS の installer と `/Applications` への配置にだけ使用します。

## 導入後確認

1. 次のようにPythonを特定し、各runtimeの版を確認します。

     ```bash
     if [ -x /Library/Frameworks/Python.framework/Versions/{python_series}/bin/python3 ]; then
         PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/{python_series}/bin/python3
     else
         PYTHON_BIN="$(command -v python3)"
     fi
     "$PYTHON_BIN" --version
     "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" --version
     "/Applications/Ollama.app/Contents/Resources/ollama" --version
     ```

2. `ollama list` に `{model}` が存在することを確認します。
3. `"$PYTHON_BIN" tools/verify_endpoint.py --url http://127.0.0.1:11434 --model {model} --require-agent --expected-context {context_length}` を実行します。
4. VS Code のモデルピッカー、Chat、Agent で実往復を確認します。

既存の VS Code/Ollama 設定と内容が異なる場合、installer は上書きせず停止します。
手動で内容を確認してマージしてください。
""", encoding="utf-8")
PY

for generated_config in \
    "$DESTINATION/config/chatLanguageModels.json" \
    "$DESTINATION/config/settings.offline.json" \
    "$DESTINATION/config/ollama-server.json"
do
    plutil -lint "$generated_config" >/dev/null || die 'generated config contains invalid JSON'
done
require_source_file 'generated docs/MACOS.md' "$DESTINATION/docs/MACOS.md"

MODEL_MANIFEST_RELATIVE="${MODEL_MANIFEST#"$OLLAMA_MODELS_SOURCE"/}"
[[ "$MODEL_MANIFEST_RELATIVE" != "$MODEL_MANIFEST" ]] || \
    die 'selected Ollama manifest is outside the model cache'
mkdir -p "$DESTINATION/models/ollama/$(dirname "$MODEL_MANIFEST_RELATIVE")"
copy_required_file 'selected Ollama model manifest' "$MODEL_MANIFEST" \
    "$DESTINATION/models/ollama/$MODEL_MANIFEST_RELATIVE"

while IFS= read -r blob_digest; do
    [[ -n "$blob_digest" ]] || continue
    blob_hex="${blob_digest#sha256:}"
    mkdir -p "$DESTINATION/models/ollama/blobs"
    copy_required_file "Ollama blob $blob_digest" \
        "$OLLAMA_MODELS_SOURCE/blobs/sha256-$blob_hex" \
        "$DESTINATION/models/ollama/blobs/sha256-$blob_hex"
done <<EOF
$BLOB_DIGESTS
EOF

if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    mkdir -p "$DESTINATION/runtime/foundry-local" "$DESTINATION/models/foundry-local"
    ditto "$FOUNDRY_MODEL_SOURCE" "$DESTINATION/models/foundry-local"
    require_source_directory 'copied Foundry Local model cache' "$DESTINATION/models/foundry-local"
fi

# Copy only artifacts already acquired and verified above; never re-download into the kit.
copy_required_file 'Python Universal2 .pkg' "$PYTHON_ARTIFACT_TEMP" \
    "$DESTINATION/$PYTHON_ARTIFACT_RELATIVE"
copy_required_file 'VS Code Apple Silicon .zip' "$VSCODE_ARTIFACT_TEMP" \
    "$DESTINATION/$VSCODE_ARTIFACT_RELATIVE"
copy_required_file 'Ollama macOS .dmg' "$OLLAMA_ARTIFACT_TEMP" \
    "$DESTINATION/$OLLAMA_ARTIFACT_RELATIVE"
if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    copy_required_file 'Foundry Local macOS arm64 pkg/zip' "$FOUNDRY_ARTIFACT_TEMP" \
        "$DESTINATION/$FOUNDRY_ARTIFACT_RELATIVE"
fi

if find "$DESTINATION" -type l -print -quit | grep -q .; then
    die 'symbolic links are forbidden in the generated kit'
fi

contains_control_character() {
    printf '%s' "$1" | LC_ALL=C grep -q '[[:cntrl:]]'
}

validate_relative_path() {
    local relative_path="$1"
    [[ -n "$relative_path" ]] || die 'empty kit-relative path'
    if contains_control_character "$relative_path"; then
        die 'control characters are forbidden in kit-relative paths'
    fi
    case "$relative_path" in
        /*|..|../*|*/../*|*\\*) die 'absolute path or path traversal detected in kit payload' ;;
    esac
}

json_quote() {
    local value="$1"
    local escaped=''
    if contains_control_character "$value"; then
        die 'control characters are forbidden in manifest values'
    fi
    escaped="$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    printf '"%s"' "$escaped"
}

directory_digest() {
    local directory="$1"
    local entries_file=''
    local sorted_file=''
    local payload_file=''
    local relative_path=''
    local content_hash=''

    entries_file="$(mktemp "$TEMP_ROOT/directory-entries.XXXXXX")"
    sorted_file="$(mktemp "$TEMP_ROOT/directory-sorted.XXXXXX")"
    while IFS= read -r -d '' payload_file; do
        relative_path="${payload_file#"$directory"/}"
        validate_relative_path "$relative_path"
        content_hash="$(file_sha256 "$payload_file")"
        printf '%s  %s\n' "$content_hash" "$relative_path" >> "$entries_file"
    done < <(find "$directory" -type f -print0)
    [[ -s "$entries_file" ]] || die 'cannot version an empty required component directory'
    LC_ALL=C sort "$entries_file" > "$sorted_file"
    file_sha256 "$sorted_file"
}

component_content_version() {
    printf 'sha256:%s' "$(file_sha256 "$1")"
}

COMPONENTS_FILE="$TEMP_ROOT/components.jsonl"
: > "$COMPONENTS_FILE"

add_component() {
    local name="$1"
    local required="$2"
    local version="$3"
    local path="$4"
    validate_relative_path "$path"
    [[ "$required" == 'true' || "$required" == 'false' ]] || die 'invalid component required flag'
    printf '{"name": %s, "required": %s, "version": %s, "path": %s}\n' \
        "$(json_quote "$name")" "$required" "$(json_quote "$version")" "$(json_quote "$path")" \
        >> "$COMPONENTS_FILE"
}

add_component 'python' true "$PYTHON_VERSION" "$PYTHON_ARTIFACT_RELATIVE"
add_component 'vscode' true "$VSCODE_VERSION" "$VSCODE_ARTIFACT_RELATIVE"
add_component 'ollama' true "$OLLAMA_ARTIFACT_VERSION" "$OLLAMA_ARTIFACT_RELATIVE"
add_component 'ollama-model' true "$MODEL_DIGEST" 'models/ollama'
add_component 'install-macos' true \
    "$(component_content_version "$DESTINATION/install-macos.sh")" 'install-macos.sh'
add_component 'chat-language-models-config' true \
    "$(component_content_version "$DESTINATION/config/chatLanguageModels.json")" \
    'config/chatLanguageModels.json'
add_component 'offline-settings-config' true \
    "$(component_content_version "$DESTINATION/config/settings.offline.json")" \
    'config/settings.offline.json'
add_component 'ollama-server-config' true \
    "$(component_content_version "$DESTINATION/config/ollama-server.json")" \
    'config/ollama-server.json'
add_component 'endpoint-verifier' true \
    "$(component_content_version "$DESTINATION/tools/verify_endpoint.py")" \
    'tools/verify_endpoint.py'
add_component 'macos-guide' true \
    "$(component_content_version "$DESTINATION/docs/MACOS.md")" 'docs/MACOS.md'

if [[ "$INCLUDE_FOUNDRY_LOCAL" -eq 1 ]]; then
    add_component 'foundry-local' true "$FOUNDRY_VERSION" "$FOUNDRY_ARTIFACT_RELATIVE"
    FOUNDRY_MODEL_VERSION="sha256:$(directory_digest "$DESTINATION/models/foundry-local")"
    add_component 'foundry-local-models' true "$FOUNDRY_MODEL_VERSION" 'models/foundry-local'
fi

PAYLOAD_PATHS="$TEMP_ROOT/payload-paths"
SORTED_PAYLOAD_PATHS="$TEMP_ROOT/payload-paths-sorted"
: > "$PAYLOAD_PATHS"
while IFS= read -r -d '' payload_file; do
    relative_path="${payload_file#"$DESTINATION"/}"
    validate_relative_path "$relative_path"
    printf '%s\n' "$relative_path" >> "$PAYLOAD_PATHS"
done < <(find "$DESTINATION" -type f -print0)
[[ -s "$PAYLOAD_PATHS" ]] || die 'generated kit contains no payload files'
LC_ALL=C sort "$PAYLOAD_PATHS" > "$SORTED_PAYLOAD_PATHS"

CREATED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
MANIFEST_TEMP="$(mktemp "$TEMP_ROOT/manifest.XXXXXX")"

{
    cat <<EOF
{
  "schemaVersion": 1,
  "createdAt": $(json_quote "$CREATED_AT"),
  "platform": "macos",
  "architecture": "arm64",
  "model": {
    "name": $(json_quote "$MODEL_NAME"),
    "digest": $(json_quote "$MODEL_DIGEST"),
    "supportsToolCalling": true
  },
  "contextLength": $CONTEXT_LENGTH,
  "components": [
EOF

    first_component=1
    while IFS= read -r component_line; do
        if [[ "$first_component" -eq 0 ]]; then
            printf ',\n'
        fi
        printf '    %s' "$component_line"
        first_component=0
    done < "$COMPONENTS_FILE"
    printf '\n  ],\n  "files": [\n'

    first_file=1
    while IFS= read -r relative_path; do
        validate_relative_path "$relative_path"
        payload_file="$DESTINATION/$relative_path"
        [[ -f "$payload_file" && ! -L "$payload_file" ]] || \
            die 'required artifact disappeared or became unsafe before manifest generation'
        byte_count="$(wc -c < "$payload_file" | tr -d '[:space:]')"
        file_hash="$(shasum -a 256 "$payload_file" | awk '{ print $1 }')"
        case "$byte_count" in
            ''|*[!0-9]*) die 'failed to determine artifact byte count' ;;
        esac
        case "$file_hash" in
            ''|*[!0-9a-f]*) die 'failed to determine artifact SHA-256' ;;
        esac
        if [[ "$first_file" -eq 0 ]]; then
            printf ',\n'
        fi
        printf '    {"path": %s, "bytes": %s, "sha256": %s}' \
            "$(json_quote "$relative_path")" "$byte_count" "$(json_quote "$file_hash")"
        first_file=0
    done < "$SORTED_PAYLOAD_PATHS"

    printf '\n  ]\n}\n'
} > "$MANIFEST_TEMP"

plutil -lint "$MANIFEST_TEMP" >/dev/null || die 'generated manifest.json is invalid JSON'

if grep -E -q '"path"[[:space:]]*:[[:space:]]*"/|"path"[[:space:]]*:[[:space:]]*"[A-Za-z]:[\\/]|\.\./' \
    "$MANIFEST_TEMP"
then
    die 'generated manifest contains an absolute path or path traversal'
fi
if grep -E -i -q '"(apiKey|password|secret|token)"[[:space:]]*:' "$MANIFEST_TEMP"; then
    die 'generated manifest contains a secret-bearing field'
fi
if [[ -n "${HOME:-}" ]] && grep -Fq "$HOME" "$MANIFEST_TEMP"; then
    die 'generated manifest contains the preparation user path'
fi

MANIFEST_PATH="$DESTINATION/manifest.json"
[[ ! -e "$MANIFEST_PATH" ]] || die 'manifest.json appeared before finalization'
ditto "$MANIFEST_TEMP" "$MANIFEST_PATH"
[[ -s "$MANIFEST_PATH" ]] || die 'manifest.json finalization failed'

printf 'Offline kit prepared successfully: %s\n' "$DESTINATION"
printf 'Model: %s (%s), context length: %s\n' "$MODEL_NAME" "$MODEL_DIGEST" "$CONTEXT_LENGTH"