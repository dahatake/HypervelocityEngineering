#!/usr/bin/env bash

# Verified offline-kit installer for macOS 14+ on Apple Silicon.
# The default mode validates and prints a plan. Only --apply changes the host.

set -euo pipefail

APPLY=0
SOURCE_INPUT=''
SOURCE_ROOT=''
MANIFEST_PATH=''
TEMP_ROOT=''
OLLAMA_MOUNT_POINT=''

schemaVersion=''
platform=''
architecture=''
MODEL_NAME=''
MODEL_DIGEST=''
supportsToolCalling=''
CONTEXT_LENGTH=''

PYTHON_VERSION=''
PYTHON_COMPONENT_PATH=''
VSCODE_VERSION=''
VSCODE_COMPONENT_PATH=''
OLLAMA_VERSION=''
OLLAMA_COMPONENT_PATH=''
OLLAMA_MODEL_COMPONENT_PATH=''
FOUNDRY_VERSION=''
FOUNDRY_COMPONENT_PATH=''
FOUNDRY_MODEL_COMPONENT_PATH=''

MANIFEST_FILE_COUNT=0
OLLAMA_MODEL_FILE_COUNT=0
FOUNDRY_MODEL_FILE_COUNT=0
LISTED_FILES=$'\n'

PYTHON_ACTION=''
PYTHON_EXISTING_PATH=''
VSCODE_ACTION=''
OLLAMA_ACTION=''
OLLAMA_MODEL_ACTION=''
CHAT_CONFIG_ACTION=''
SETTINGS_CONFIG_ACTION=''
OLLAMA_CONFIG_ACTION=''
CONTEXT_ACTION=''
FOUNDRY_ACTION='none'
FOUNDRY_MODEL_ACTION='none'

VSCODE_APP='/Applications/Visual Studio Code.app'
OLLAMA_APP='/Applications/Ollama.app'
OLLAMA_URL='http://127.0.0.1:11434'

usage() {
    cat <<'USAGE'
Usage:
  install-macos.sh [--source PATH] [--apply]

Options:
  --source PATH  Offline-kit root. Default: the directory containing this script.
  --apply        Install after every integrity and conflict preflight succeeds.
  -h, --help     Show this help.

Without --apply, the script performs read-only validation and prints the plan.
USAGE
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

die_status() {
    local status="$1"
    shift
    printf 'ERROR: %s\n' "$*" >&2
    exit "$status"
}

plan() {
    printf '    [PLAN] %s\n' "$*"
}

cleanup() {
    local status=$?
    local cleanup_failed=0

    trap - EXIT HUP INT TERM
    if [[ -n "$OLLAMA_MOUNT_POINT" && -d "$OLLAMA_MOUNT_POINT" ]]; then
        if ! hdiutil detach "$OLLAMA_MOUNT_POINT" >/dev/null; then
            printf 'ERROR: failed to detach the verified Ollama disk image\n' >&2
            cleanup_failed=1
        fi
        OLLAMA_MOUNT_POINT=''
    fi
    if [[ -n "$TEMP_ROOT" && -d "$TEMP_ROOT" ]]; then
        if ! rm -rf "$TEMP_ROOT"; then
            printf 'ERROR: failed to remove the installer temporary directory\n' >&2
            cleanup_failed=1
        fi
        TEMP_ROOT=''
    fi
    if [[ "$status" -eq 0 && "$cleanup_failed" -ne 0 ]]; then
        status=1
    fi
    exit "$status"
}

on_signal() {
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
        --source)
            [[ $# -ge 2 ]] || die '--source requires a value'
            require_option_value '--source' "$2"
            SOURCE_INPUT="$2"
            shift 2
            ;;
        --source=*)
            SOURCE_INPUT="${1#*=}"
            require_option_value '--source' "$SOURCE_INPUT"
            shift
            ;;
        --apply)
            APPLY=1
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

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required macOS command is unavailable: $1"
}

for required_command in \
    awk bash cat chmod cmp curl dirname ditto find grep hdiutil installer launchctl \
    ln mkdir mktemp nc open pgrep plutil rm sed shasum sleep sudo tr uname wc
do
    require_command "$required_command"
done
require_command sw_vers

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

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -z "$SOURCE_INPUT" ]]; then
    SOURCE_INPUT="$SCRIPT_DIR"
fi

[[ -e "$SOURCE_INPUT" ]] || die "offline-kit source is missing: $SOURCE_INPUT"
[[ -d "$SOURCE_INPUT" ]] || die "offline-kit source is not a directory: $SOURCE_INPUT"
[[ ! -L "$SOURCE_INPUT" ]] || die 'offline-kit source must not be a symbolic link'
SOURCE_ROOT="$(CDPATH='' cd -- "$SOURCE_INPUT" && pwd -P)"
MANIFEST_PATH="$SOURCE_ROOT/manifest.json"

[[ -f "$MANIFEST_PATH" ]] || die "manifest.json is missing: $MANIFEST_PATH"
[[ ! -L "$MANIFEST_PATH" ]] || die 'manifest.json must not be a symbolic link'

FIRST_SYMLINK="$(find "$SOURCE_ROOT" -type l -print -quit)"
[[ -z "$FIRST_SYMLINK" ]] || die "symbolic links are forbidden in the offline kit: $FIRST_SYMLINK"
FIRST_SPECIAL_NODE="$(find "$SOURCE_ROOT" ! -type d ! -type f ! -type l -print -quit)"
[[ -z "$FIRST_SPECIAL_NODE" ]] || die "unsupported filesystem node in the offline kit: $FIRST_SPECIAL_NODE"

plutil -lint "$MANIFEST_PATH" >/dev/null || die 'manifest.json is not valid JSON/property-list data'

PLUTIL_VALUE=''
manifest_value() {
    local key_path="$1"
    local expected_type="$2"

    if ! PLUTIL_VALUE="$(plutil -extract "$key_path" raw -expect "$expected_type" -o - "$MANIFEST_PATH")"; then
        die "manifest field is missing or has the wrong type: $key_path"
    fi
}

manifest_entry_exists() {
    plutil -extract "$1" json -o - "$MANIFEST_PATH" >/dev/null 2>&1
}

contains_control_character() {
    printf '%s' "$1" | LC_ALL=C grep -q '[[:cntrl:]]'
}

validate_metadata_text() {
    local label="$1"
    local value="$2"

    [[ -n "$value" ]] || die "manifest field must not be empty: $label"
    if contains_control_character "$value"; then
        die "manifest field contains a control character: $label"
    fi
}

validate_component_version() {
    local label="$1"
    local value="$2"

    validate_metadata_text "$label" "$value"
    case "$value" in
        *[!A-Za-z0-9._+-]*) die "manifest component version is unsafe: $label" ;;
    esac
}

validate_relative_path() {
    local relative_path="$1"

    [[ -n "$relative_path" ]] || die 'manifest contains an empty file path'
    if contains_control_character "$relative_path"; then
        die 'manifest contains an unsafe path with a control character'
    fi
    case "$relative_path" in /*) die "manifest contains an absolute path: $relative_path" ;;
        .|..|./*|../*|*/./*|*/../*|*/.|*/..)
            die "manifest contains path traversal or a non-canonical path: $relative_path"
            ;;
        *//*|*\\*) die "manifest contains an unsafe path: $relative_path" ;;
    esac
}

listed_contains() {
    local relative_path="$1"
    case "$LISTED_FILES" in
        *$'\n'"$relative_path"$'\n'*) return 0 ;;
    esac
    return 1
}

manifest_value 'schemaVersion' integer
schemaVersion="$PLUTIL_VALUE"
[[ "$schemaVersion" == '1' ]] || die 'manifest schemaVersion must equal 1'

manifest_value 'createdAt' string
CREATED_AT="$PLUTIL_VALUE"
validate_metadata_text 'createdAt' "$CREATED_AT"

manifest_value 'platform' string
platform="$PLUTIL_VALUE"
[[ "$platform" == 'macos' ]] || die 'manifest platform must equal macos'

manifest_value 'architecture' string
architecture="$PLUTIL_VALUE"
[[ "$architecture" == 'arm64' ]] || die 'manifest architecture must equal arm64'

manifest_value 'model.name' string
MODEL_NAME="$PLUTIL_VALUE"
validate_metadata_text 'model.name' "$MODEL_NAME"
case "$MODEL_NAME" in
    *[!A-Za-z0-9._:/@-]*|/*|*'..'*|*/*/*)
        die 'manifest model.name is unsafe or unsupported'
        ;;
esac

manifest_value 'model.digest' string
MODEL_DIGEST="$PLUTIL_VALUE"
case "$MODEL_DIGEST" in
    ''|*[!0-9a-f]*) die 'manifest model.digest must be lowercase hexadecimal' ;;
esac
if [[ ${#MODEL_DIGEST} -lt 12 || ${#MODEL_DIGEST} -gt 64 ]]; then
    die 'manifest model.digest has an invalid length'
fi

manifest_value 'model.supportsToolCalling' bool
supportsToolCalling="$PLUTIL_VALUE"
[[ "$supportsToolCalling" == 'true' ]] || die 'model.supportsToolCalling must equal true for an Agent kit'

manifest_value 'contextLength' integer
CONTEXT_LENGTH="$PLUTIL_VALUE"
case "$CONTEXT_LENGTH" in
    ''|*[!0-9]*|0*) die 'manifest contextLength must be a canonical positive integer' ;;
esac
[[ ${#CONTEXT_LENGTH} -le 9 ]] || die 'manifest contextLength is too large'
[[ "$CONTEXT_LENGTH" -ge 1 ]] || die 'manifest contextLength must be positive'

plutil -extract components json -expect array -o - "$MANIFEST_PATH" >/dev/null || \
    die 'manifest components must be an array'
plutil -extract files json -expect array -o - "$MANIFEST_PATH" >/dev/null || \
    die 'manifest files must be an array'

COMPONENT_INDEX=0
while manifest_entry_exists "components.${COMPONENT_INDEX}"; do
    manifest_value "components.${COMPONENT_INDEX}.name" string
    component_name="$PLUTIL_VALUE"
    manifest_value "components.${COMPONENT_INDEX}.required" bool
    component_required="$PLUTIL_VALUE"
    manifest_value "components.${COMPONENT_INDEX}.version" string
    component_version="$PLUTIL_VALUE"
    manifest_value "components.${COMPONENT_INDEX}.path" string
    component_path="$PLUTIL_VALUE"

    validate_metadata_text "components.${COMPONENT_INDEX}.name" "$component_name"
    validate_metadata_text "components.${COMPONENT_INDEX}.version" "$component_version"
    validate_relative_path "$component_path"
    case "$component_required" in
        true|false) ;;
        *) die "invalid required flag for component: $component_name" ;;
    esac

    case "$component_name" in
        python)
            [[ -z "$PYTHON_COMPONENT_PATH" ]] || die 'duplicate python component'
            [[ "$component_required" == 'true' ]] || die 'python component must be required'
            case "$component_path" in
                runtime/python/*.pkg) ;;
                *) die 'python component must be a runtime/python .pkg' ;;
            esac
            validate_component_version 'python' "$component_version"
            PYTHON_VERSION="$component_version"
            PYTHON_COMPONENT_PATH="$component_path"
            ;;
        vscode)
            [[ -z "$VSCODE_COMPONENT_PATH" ]] || die 'duplicate vscode component'
            [[ "$component_required" == 'true' ]] || die 'vscode component must be required'
            case "$component_path" in
                runtime/vscode/*.zip) ;;
                *) die 'vscode component must be a runtime/vscode .zip' ;;
            esac
            validate_component_version 'vscode' "$component_version"
            VSCODE_VERSION="$component_version"
            VSCODE_COMPONENT_PATH="$component_path"
            ;;
        ollama)
            [[ -z "$OLLAMA_COMPONENT_PATH" ]] || die 'duplicate ollama component'
            [[ "$component_required" == 'true' ]] || die 'ollama component must be required'
            case "$component_path" in
                runtime/ollama/*.dmg) ;;
                *) die 'ollama component must be a runtime/ollama .dmg' ;;
            esac
            validate_component_version 'ollama' "$component_version"
            OLLAMA_VERSION="$component_version"
            OLLAMA_COMPONENT_PATH="$component_path"
            ;;
        ollama-model)
            [[ -z "$OLLAMA_MODEL_COMPONENT_PATH" ]] || die 'duplicate ollama-model component'
            [[ "$component_required" == 'true' ]] || die 'ollama-model component must be required'
            [[ "$component_path" == 'models/ollama' ]] || \
                die 'ollama-model component path must equal models/ollama'
            OLLAMA_MODEL_COMPONENT_PATH="$component_path"
            ;;
        foundry-local)
            [[ -z "$FOUNDRY_COMPONENT_PATH" ]] || die 'duplicate foundry-local component'
            [[ "$component_required" == 'true' ]] || \
                die 'selected foundry-local component must be required'
            case "$component_path" in
                runtime/foundry-local/*.pkg|runtime/foundry-local/*.zip) ;;
                *) die 'foundry-local component must be a runtime/foundry-local pkg or zip' ;;
            esac
            validate_component_version 'foundry-local' "$component_version"
            FOUNDRY_VERSION="$component_version"
            FOUNDRY_COMPONENT_PATH="$component_path"
            ;;
        foundry-local-models)
            [[ -z "$FOUNDRY_MODEL_COMPONENT_PATH" ]] || \
                die 'duplicate foundry-local-models component'
            [[ "$component_required" == 'true' ]] || \
                die 'selected foundry-local-models component must be required'
            [[ "$component_path" == 'models/foundry-local' ]] || \
                die 'foundry-local-models path must equal models/foundry-local'
            FOUNDRY_MODEL_COMPONENT_PATH="$component_path"
            ;;
    esac

    COMPONENT_INDEX=$((COMPONENT_INDEX + 1))
done

[[ "$COMPONENT_INDEX" -gt 0 ]] || die 'manifest components array must not be empty'
[[ -n "$PYTHON_COMPONENT_PATH" ]] || die 'required python component is missing'
[[ -n "$VSCODE_COMPONENT_PATH" ]] || die 'required vscode component is missing'
[[ -n "$OLLAMA_COMPONENT_PATH" ]] || die 'required ollama component is missing'
[[ -n "$OLLAMA_MODEL_COMPONENT_PATH" ]] || die 'required ollama-model component is missing'
if [[ -n "$FOUNDRY_COMPONENT_PATH" && -z "$FOUNDRY_MODEL_COMPONENT_PATH" ]]; then
    die 'Foundry Local runtime requires the Foundry Local model cache component'
fi
if [[ -z "$FOUNDRY_COMPONENT_PATH" && -n "$FOUNDRY_MODEL_COMPONENT_PATH" ]]; then
    die 'Foundry Local model cache requires the Foundry Local runtime component'
fi

while manifest_entry_exists "files.${MANIFEST_FILE_COUNT}"; do
    manifest_value "files.${MANIFEST_FILE_COUNT}.path" string
    relative_path="$PLUTIL_VALUE"
    manifest_value "files.${MANIFEST_FILE_COUNT}.bytes" integer
    expected_bytes="$PLUTIL_VALUE"
    manifest_value "files.${MANIFEST_FILE_COUNT}.sha256" string
    expected_sha256="$PLUTIL_VALUE"

    validate_relative_path "$relative_path"
    [[ "$relative_path" != 'manifest.json' ]] || \
        die 'manifest.json must not list or hash itself'
    listed_contains "$relative_path" && die "duplicate manifest file path: $relative_path"
    case "$expected_bytes" in
        ''|*[!0-9]*|0[0-9]*) die "invalid byte count for manifest file: $relative_path" ;;
    esac
    case "$expected_sha256" in
        *[!0-9a-f]*) die "invalid SHA-256 for manifest file: $relative_path" ;;
    esac
    [[ ${#expected_sha256} -eq 64 ]] || \
        die "invalid SHA-256 length for manifest file: $relative_path"

    payload_path="$SOURCE_ROOT/$relative_path"
    if [[ ! -f "$payload_path" ]]; then
        die "missing manifest-listed file or non-regular payload: $relative_path"
    fi
    [[ ! -L "$payload_path" ]] || die "symbolic link is forbidden: $relative_path"

    actual_bytes="$(wc -c < "$payload_path" | tr -d '[:space:]')"
    [[ "$actual_bytes" == "$expected_bytes" ]] || \
        die "byte-count mismatch for manifest file: $relative_path"
    actual_sha256="$(shasum -a 256 "$payload_path" | awk '{ print $1 }')"
    [[ "$actual_sha256" == "$expected_sha256" ]] || \
        die "SHA-256 mismatch for manifest file: $relative_path"

    LISTED_FILES="${LISTED_FILES}${relative_path}"$'\n'
    case "$relative_path" in
        "$OLLAMA_MODEL_COMPONENT_PATH"/*)
            OLLAMA_MODEL_FILE_COUNT=$((OLLAMA_MODEL_FILE_COUNT + 1))
            ;;
    esac
    if [[ -n "$FOUNDRY_MODEL_COMPONENT_PATH" ]]; then
        case "$relative_path" in
            "$FOUNDRY_MODEL_COMPONENT_PATH"/*)
                FOUNDRY_MODEL_FILE_COUNT=$((FOUNDRY_MODEL_FILE_COUNT + 1))
                ;;
        esac
    fi
    MANIFEST_FILE_COUNT=$((MANIFEST_FILE_COUNT + 1))
done

[[ "$MANIFEST_FILE_COUNT" -gt 0 ]] || die 'manifest files array must not be empty'
[[ "$OLLAMA_MODEL_FILE_COUNT" -gt 0 ]] || die 'manifest lists no Ollama model-cache files'
if [[ -n "$FOUNDRY_MODEL_COMPONENT_PATH" && "$FOUNDRY_MODEL_FILE_COUNT" -eq 0 ]]; then
    die 'manifest lists no Foundry Local model-cache files'
fi

require_listed_file() {
    local relative_path="$1"
    listed_contains "$relative_path" || die "required file is absent from manifest.files: $relative_path"
}

require_listed_file "$PYTHON_COMPONENT_PATH"
require_listed_file "$VSCODE_COMPONENT_PATH"
require_listed_file "$OLLAMA_COMPONENT_PATH"
require_listed_file 'config/chatLanguageModels.json'
require_listed_file 'config/settings.offline.json'
require_listed_file 'config/ollama-server.json'
require_listed_file 'tools/verify_endpoint.py'
if [[ -n "$FOUNDRY_COMPONENT_PATH" ]]; then
    require_listed_file "$FOUNDRY_COMPONENT_PATH"
fi

VERIFY_SCRIPT="$SOURCE_ROOT/tools/verify_endpoint.py"
[[ -f "$SOURCE_ROOT/tools/verify_endpoint.py" && ! -L "$VERIFY_SCRIPT" && -s "$VERIFY_SCRIPT" ]] || \
    die 'required tools/verify_endpoint.py is missing, empty, or unsafe'
for required_runtime_file in \
    "$SOURCE_ROOT/$PYTHON_COMPONENT_PATH" \
    "$SOURCE_ROOT/$VSCODE_COMPONENT_PATH" \
    "$SOURCE_ROOT/$OLLAMA_COMPONENT_PATH"
do
    [[ -f "$required_runtime_file" && ! -L "$required_runtime_file" && -s "$required_runtime_file" ]] || \
        die "required runtime is missing, empty, or unsafe: $required_runtime_file"
done
if [[ -n "$FOUNDRY_COMPONENT_PATH" ]]; then
    [[ -f "$SOURCE_ROOT/$FOUNDRY_COMPONENT_PATH" && \
       ! -L "$SOURCE_ROOT/$FOUNDRY_COMPONENT_PATH" && \
       -s "$SOURCE_ROOT/$FOUNDRY_COMPONENT_PATH" ]] || \
        die 'required Foundry Local runtime is missing, empty, or unsafe'
fi
[[ -d "$SOURCE_ROOT/models/ollama" && ! -L "$SOURCE_ROOT/models/ollama" ]] || \
    die 'required models/ollama cache directory is missing or unsafe'
if [[ -n "$FOUNDRY_MODEL_COMPONENT_PATH" ]]; then
    [[ -d "$SOURCE_ROOT/models/foundry-local" && ! -L "$SOURCE_ROOT/models/foundry-local" ]] || \
        die 'required models/foundry-local cache directory is missing or unsafe'
fi

ACTUAL_FILE_COUNT=0
while IFS= read -r -d '' actual_file; do
    actual_relative="${actual_file#"$SOURCE_ROOT"/}"
    if [[ "$actual_relative" == 'manifest.json' ]]; then
        continue
    fi
    validate_relative_path "$actual_relative"
    listed_contains "$actual_relative" || \
        die "extra unlisted file detected in offline kit: $actual_relative"
    ACTUAL_FILE_COUNT=$((ACTUAL_FILE_COUNT + 1))
done < <(find "$SOURCE_ROOT" -type f -print0)
[[ "$ACTUAL_FILE_COUNT" -eq "$MANIFEST_FILE_COUNT" ]] || \
    die 'extra, missing, or duplicate file count detected after manifest verification'

FIRST_SYMLINK="$(find "$SOURCE_ROOT" -type l -print -quit)"
[[ -z "$FIRST_SYMLINK" ]] || die "symbolic link appeared during verification: $FIRST_SYMLINK"

extract_version() {
    awk '
        {
            for (i = 1; i <= NF; i++) {
                token = $i
                sub(/^[^0-9]*/, "", token)
                sub(/[^0-9A-Za-z.+-].*$/, "", token)
                if (token ~ /^[0-9]+\.[0-9]+(\.[0-9]+)?([-+][0-9A-Za-z.-]+)?$/) {
                    print token
                    exit
                }
            }
        }
    '
}

runtime_version() {
    local executable="$1"
    local label="$2"
    local output=''

    if ! output="$("$executable" --version 2>&1)"; then
        die "unable to inspect existing $label version"
    fi
    RUNTIME_VERSION="$(printf '%s\n' "$output" | extract_version)"
    [[ -n "$RUNTIME_VERSION" ]] || die "unable to parse existing $label version"
}

existing_app_version() {
    local app_path="$1"
    local label="$2"
    local plist_path="$app_path/Contents/Info.plist"

    [[ -d "$app_path" && ! -L "$app_path" ]] || \
        die "existing $label path is not a safe application bundle; manual merge/removal is required"
    [[ -f "$plist_path" && ! -L "$plist_path" ]] || \
        die "existing $label has no safe Info.plist; manual merge/removal is required"
    if ! APP_VERSION="$(plutil -extract CFBundleShortVersionString raw -expect string -o - "$plist_path")"; then
        die "unable to inspect existing $label version; manual merge/removal is required"
    fi
    validate_metadata_text "$label version" "$APP_VERSION"
}

assert_safe_destination_parent() {
    local destination_path="$1"
    local label="$2"
    local current_path="${destination_path%/*}"

    [[ "$destination_path" == /* && -n "$current_path" ]] || \
        die "$label destination must be an absolute path"
    while [[ -n "$current_path" ]]; do
        if [[ -L "$current_path" ]]; then
            die "$label destination parent is a symbolic link; manual merge/removal is required: $current_path"
        fi
        if [[ -e "$current_path" && ! -d "$current_path" ]]; then
            die "$label destination parent is not a directory; manual merge/removal is required: $current_path"
        fi
        [[ "$current_path" == '/' ]] && break
        current_path="${current_path%/*}"
        [[ -n "$current_path" ]] || current_path='/'
    done
}

PYTHON_VERSION_REMAINDER="${PYTHON_VERSION#*.}"
PYTHON_MAJOR="${PYTHON_VERSION%%.*}"
PYTHON_MINOR="${PYTHON_VERSION_REMAINDER%%.*}"
case "$PYTHON_MAJOR" in ''|*[!0-9]*) die 'python component version has no numeric major version' ;; esac
case "$PYTHON_MINOR" in ''|*[!0-9]*) die 'python component version has no numeric minor version' ;; esac
PYTHON_PACKAGE_BIN="/Library/Frameworks/Python.framework/Versions/${PYTHON_MAJOR}.${PYTHON_MINOR}/bin/python3"
assert_safe_destination_parent "$PYTHON_PACKAGE_BIN" 'Python'
assert_safe_destination_parent "$VSCODE_APP" 'VS Code'
assert_safe_destination_parent "$OLLAMA_APP" 'Ollama'

if [[ -x "$PYTHON_PACKAGE_BIN" ]]; then
    PYTHON_EXISTING_PATH="$PYTHON_PACKAGE_BIN"
elif PYTHON_EXISTING_PATH="$(command -v python3 2>/dev/null)"; then
    :
else
    PYTHON_EXISTING_PATH=''
fi
if [[ -n "$PYTHON_EXISTING_PATH" ]]; then
    [[ -x "$PYTHON_EXISTING_PATH" ]] || die 'existing python3 is not executable'
    runtime_version "$PYTHON_EXISTING_PATH" 'Python'
    if [[ "$RUNTIME_VERSION" == "$PYTHON_VERSION" ]]; then
        PYTHON_ACTION='skip'
    else
        die "existing Python $RUNTIME_VERSION conflicts with kit version $PYTHON_VERSION; manual merge/removal is required"
    fi
else
    PYTHON_ACTION='install'
fi

if [[ -e "$VSCODE_APP" || -L "$VSCODE_APP" ]]; then
    existing_app_version "$VSCODE_APP" 'VS Code'
    if [[ "$APP_VERSION" == "$VSCODE_VERSION" ]]; then
        VSCODE_ACTION='skip'
    else
        die "existing VS Code $APP_VERSION conflicts with kit version $VSCODE_VERSION; manual merge/removal is required"
    fi
else
    VSCODE_ACTION='install'
fi

if [[ -e "$OLLAMA_APP" || -L "$OLLAMA_APP" ]]; then
    existing_app_version "$OLLAMA_APP" 'Ollama'
    if [[ "$APP_VERSION" == "$OLLAMA_VERSION" ]]; then
        OLLAMA_ACTION='skip'
    else
        die "existing Ollama $APP_VERSION conflicts with kit version $OLLAMA_VERSION; manual merge/removal is required"
    fi
else
    OLLAMA_ACTION='install'
fi

if pgrep -x Ollama >/dev/null 2>&1 || pgrep -x ollama >/dev/null 2>&1; then
    die 'an Ollama process is already running; quit it before dry-run or Apply'
fi
if nc -z -w 1 127.0.0.1 11434 >/dev/null 2>&1; then
    die 'Ollama endpoint port 11434 is already in use; quit the existing process before dry-run or Apply'
fi

manifest_subtree_matches() {
    local manifest_prefix="$1"
    local destination_root="$2"
    local index=0
    local expected_count=0
    local target_path=''
    local suffix=''
    local path_value=''
    local hash_value=''
    local current_hash=''
    local destination_file=''
    local destination_relative=''

    [[ -d "$destination_root" && ! -L "$destination_root" ]] || return 1
    if [[ -n "$(find "$destination_root" -type l -print -quit)" ]]; then
        return 1
    fi
    if [[ -n "$(find "$destination_root" ! -type d ! -type f ! -type l -print -quit)" ]]; then
        return 1
    fi

    while manifest_entry_exists "files.${index}"; do
        manifest_value "files.${index}.path" string
        path_value="$PLUTIL_VALUE"
        case "$path_value" in
            "$manifest_prefix"/*)
                suffix="${path_value#"$manifest_prefix"/}"
                target_path="$destination_root/$suffix"
                [[ -f "$target_path" && ! -L "$target_path" ]] || return 1
                manifest_value "files.${index}.sha256" string
                hash_value="$PLUTIL_VALUE"
                current_hash="$(shasum -a 256 "$target_path" | awk '{ print $1 }')"
                [[ "$current_hash" == "$hash_value" ]] || return 1
                expected_count=$((expected_count + 1))
                ;;
        esac
        index=$((index + 1))
    done
    [[ "$expected_count" -gt 0 ]] || return 1

    while IFS= read -r -d '' destination_file; do
        destination_relative="${destination_file#"$destination_root"/}"
        if contains_control_character "$destination_relative"; then
            return 1
        fi
        listed_contains "$manifest_prefix/$destination_relative" || return 1
    done < <(find "$destination_root" -type f -print0)
    return 0
}

[[ -n "${HOME:-}" ]] || die 'HOME is required for user-scoped model and configuration paths'
[[ "$HOME" == /* ]] || die 'HOME must be an absolute path'
[[ -d "$HOME" && ! -L "$HOME" ]] || die 'HOME must be a safe existing directory'

OLLAMA_MODELS_DEST="$HOME/.ollama/models"
assert_safe_destination_parent "$OLLAMA_MODELS_DEST" 'Ollama model cache'
if [[ -e "$OLLAMA_MODELS_DEST" || -L "$OLLAMA_MODELS_DEST" ]]; then
    if manifest_subtree_matches "$OLLAMA_MODEL_COMPONENT_PATH" "$OLLAMA_MODELS_DEST"; then
        OLLAMA_MODEL_ACTION='skip'
    else
        die "existing Ollama model cache conflicts with the verified kit; manual merge is required: $OLLAMA_MODELS_DEST"
    fi
else
    OLLAMA_MODEL_ACTION='install'
fi

preflight_config_file() {
    local source_path="$1"
    local destination_path="$2"
    local label="$3"

    [[ -f "$source_path" && ! -L "$source_path" ]] || die "required config source is missing: $label"
    if [[ -e "$destination_path" || -L "$destination_path" ]]; then
        [[ -f "$destination_path" && ! -L "$destination_path" ]] || \
            die "existing $label destination is unsafe; manual merge/removal is required"
        if cmp -s "$source_path" "$destination_path"; then
            PREFLIGHT_ACTION='skip'
        else
            die "existing $label conflicts with the verified kit; manual merge is required: $destination_path"
        fi
    else
        PREFLIGHT_ACTION='install'
    fi
}

VSCODE_USER_DIR="$HOME/Library/Application Support/Code/User"
CHAT_CONFIG_SOURCE="$SOURCE_ROOT/config/chatLanguageModels.json"
CHAT_CONFIG_DEST="$VSCODE_USER_DIR/chatLanguageModels.json"
SETTINGS_CONFIG_SOURCE="$SOURCE_ROOT/config/settings.offline.json"
SETTINGS_CONFIG_DEST="$VSCODE_USER_DIR/settings.json"
OLLAMA_CONFIG_SOURCE="$SOURCE_ROOT/config/ollama-server.json"
OLLAMA_CONFIG_DEST="$HOME/.ollama/server.json"

for config_source in \
    "$CHAT_CONFIG_SOURCE" \
    "$SETTINGS_CONFIG_SOURCE" \
    "$OLLAMA_CONFIG_SOURCE"
do
    plutil -lint "$config_source" >/dev/null || \
        die "verified config payload is not valid JSON: $config_source"
done
assert_safe_destination_parent "$CHAT_CONFIG_DEST" 'chatLanguageModels.json'
assert_safe_destination_parent "$SETTINGS_CONFIG_DEST" 'VS Code settings.json'
assert_safe_destination_parent "$OLLAMA_CONFIG_DEST" 'Ollama server.json'
preflight_config_file "$CHAT_CONFIG_SOURCE" "$CHAT_CONFIG_DEST" 'chatLanguageModels.json'
CHAT_CONFIG_ACTION="$PREFLIGHT_ACTION"
preflight_config_file "$SETTINGS_CONFIG_SOURCE" "$SETTINGS_CONFIG_DEST" 'VS Code settings.json'
SETTINGS_CONFIG_ACTION="$PREFLIGHT_ACTION"
preflight_config_file "$OLLAMA_CONFIG_SOURCE" "$OLLAMA_CONFIG_DEST" 'Ollama server.json'
OLLAMA_CONFIG_ACTION="$PREFLIGHT_ACTION"

if [[ -n "${OLLAMA_CONTEXT_LENGTH+x}" && "$OLLAMA_CONTEXT_LENGTH" != "$CONTEXT_LENGTH" ]]; then
    die "current OLLAMA_CONTEXT_LENGTH conflicts with manifest contextLength; manual environment merge is required"
fi
LAUNCHCTL_CONTEXT=''
if LAUNCHCTL_CONTEXT="$(launchctl getenv OLLAMA_CONTEXT_LENGTH 2>/dev/null)"; then
    :
else
    LAUNCHCTL_CONTEXT=''
fi
if [[ -z "$LAUNCHCTL_CONTEXT" ]]; then
    CONTEXT_ACTION='set'
elif [[ "$LAUNCHCTL_CONTEXT" == "$CONTEXT_LENGTH" ]]; then
    CONTEXT_ACTION='skip'
else
    die "launchctl OLLAMA_CONTEXT_LENGTH=$LAUNCHCTL_CONTEXT conflicts with manifest contextLength=$CONTEXT_LENGTH; manual environment merge is required"
fi

FOUNDRY_MODELS_DEST="$HOME/.foundry/cache/models"
FOUNDRY_ZIP_DEST=''
FOUNDRY_BIN_LINK='/usr/local/bin/foundry'
if [[ -n "$FOUNDRY_COMPONENT_PATH" ]]; then
    assert_safe_destination_parent "$FOUNDRY_MODELS_DEST" 'Foundry Local model cache'
    FOUNDRY_EXISTING_PATH=''
    if FOUNDRY_EXISTING_PATH="$(command -v foundry 2>/dev/null)"; then
        [[ -x "$FOUNDRY_EXISTING_PATH" ]] || die 'existing foundry command is not executable'
        runtime_version "$FOUNDRY_EXISTING_PATH" 'Foundry Local'
        if [[ "$RUNTIME_VERSION" == "$FOUNDRY_VERSION" ]]; then
            FOUNDRY_ACTION='skip'
        else
            die "existing Foundry Local $RUNTIME_VERSION conflicts with kit version $FOUNDRY_VERSION; manual merge/removal is required"
        fi
    else
        FOUNDRY_ACTION='install'
    fi

    case "$FOUNDRY_COMPONENT_PATH" in
        *.pkg) ;;
        *.zip)
            FOUNDRY_ZIP_DEST="/usr/local/libexec/foundrylocal/$FOUNDRY_VERSION"
            assert_safe_destination_parent "$FOUNDRY_ZIP_DEST" 'Foundry Local runtime'
            assert_safe_destination_parent "$FOUNDRY_BIN_LINK" 'Foundry Local command'
            if [[ "$FOUNDRY_ACTION" == 'install' ]]; then
                if [[ -e "$FOUNDRY_ZIP_DEST" || -L "$FOUNDRY_ZIP_DEST" || \
                      -e "$FOUNDRY_BIN_LINK" || -L "$FOUNDRY_BIN_LINK" ]]; then
                    die 'existing Foundry Local zip destination conflicts with the kit; manual merge/removal is required'
                fi
            fi
            ;;
    esac

    if [[ -e "$FOUNDRY_MODELS_DEST" || -L "$FOUNDRY_MODELS_DEST" ]]; then
        if manifest_subtree_matches "$FOUNDRY_MODEL_COMPONENT_PATH" "$FOUNDRY_MODELS_DEST"; then
            FOUNDRY_MODEL_ACTION='skip'
        else
            die "existing Foundry Local model cache conflicts with the verified kit; manual merge is required: $FOUNDRY_MODELS_DEST"
        fi
    else
        FOUNDRY_MODEL_ACTION='install'
    fi
fi

printf 'Verified offline kit: %s\n' "$SOURCE_ROOT"
printf '  createdAt: %s\n' "$CREATED_AT"
printf '  model: %s (%s)\n' "$MODEL_NAME" "$MODEL_DIGEST"
printf '  contextLength: %s\n' "$CONTEXT_LENGTH"
plan "Python $PYTHON_VERSION: $PYTHON_ACTION"
plan "VS Code $VSCODE_VERSION: $VSCODE_ACTION"
plan "Ollama $OLLAMA_VERSION: $OLLAMA_ACTION"
plan "Ollama model cache -> $OLLAMA_MODELS_DEST: $OLLAMA_MODEL_ACTION"
plan "config/chatLanguageModels.json -> $CHAT_CONFIG_DEST: $CHAT_CONFIG_ACTION"
plan "config/settings.offline.json -> $SETTINGS_CONFIG_DEST: $SETTINGS_CONFIG_ACTION"
plan "config/ollama-server.json -> $OLLAMA_CONFIG_DEST: $OLLAMA_CONFIG_ACTION"
plan "launchctl setenv OLLAMA_CONTEXT_LENGTH $CONTEXT_LENGTH: $CONTEXT_ACTION"
if [[ -n "$FOUNDRY_COMPONENT_PATH" ]]; then
    plan "Foundry Local $FOUNDRY_VERSION: $FOUNDRY_ACTION"
    plan "Foundry Local model cache -> $FOUNDRY_MODELS_DEST: $FOUNDRY_MODEL_ACTION"
fi
plan 'open -a Ollama, wait for finite loopback readiness, then run Agent verification'

if [[ "$APPLY" -eq 0 ]]; then
    printf '\nDRY-RUN complete: no installation, copy, environment change, or application launch was performed.\n'
    printf 'Re-run with --apply only after reviewing every planned action.\n'
    exit 0
fi

FIRST_SYMLINK="$(find "$SOURCE_ROOT" -type l -print -quit)"
[[ -z "$FIRST_SYMLINK" ]] || die "symbolic link appeared before Apply: $FIRST_SYMLINK"

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/install-macos.XXXXXX")"
[[ -d "$TEMP_ROOT" ]] || die 'failed to create installer temporary directory'

if [[ "$PYTHON_ACTION" == 'install' ]]; then
    sudo installer -pkg "$SOURCE_ROOT/$PYTHON_COMPONENT_PATH" -target /
fi

if [[ "$VSCODE_ACTION" == 'install' ]]; then
    VSCODE_EXPANDED="$TEMP_ROOT/vscode"
    mkdir -p "$VSCODE_EXPANDED"
    ditto -x -k "$SOURCE_ROOT/$VSCODE_COMPONENT_PATH" "$VSCODE_EXPANDED"
    VSCODE_SOURCE_APP="$VSCODE_EXPANDED/Visual Studio Code.app"
    [[ -d "$VSCODE_SOURCE_APP" ]] || die 'verified VS Code zip does not contain Visual Studio Code.app'
    [[ ! -e "$VSCODE_APP" && ! -L "$VSCODE_APP" ]] || \
        die 'VS Code destination appeared after preflight; manual merge/removal is required'
    sudo ditto "$VSCODE_SOURCE_APP" "$VSCODE_APP"
fi

if [[ "$OLLAMA_ACTION" == 'install' ]]; then
    OLLAMA_MOUNT_POINT="$TEMP_ROOT/ollama-mount"
    mkdir -p "$OLLAMA_MOUNT_POINT"
    hdiutil attach "$SOURCE_ROOT/$OLLAMA_COMPONENT_PATH" \
        -nobrowse -readonly -mountpoint "$OLLAMA_MOUNT_POINT" >/dev/null
    OLLAMA_SOURCE_APP="$OLLAMA_MOUNT_POINT/Ollama.app"
    [[ -d "$OLLAMA_SOURCE_APP" ]] || die 'verified Ollama dmg does not contain Ollama.app'
    [[ ! -e "$OLLAMA_APP" && ! -L "$OLLAMA_APP" ]] || \
        die 'Ollama destination appeared after preflight; manual merge/removal is required'
    sudo ditto "$OLLAMA_SOURCE_APP" "$OLLAMA_APP"
    hdiutil detach "$OLLAMA_MOUNT_POINT" >/dev/null
    OLLAMA_MOUNT_POINT=''
fi

install_foundry_runtime() {
    local foundry_source="$SOURCE_ROOT/$FOUNDRY_COMPONENT_PATH"
    local foundry_expanded=''

    case "$FOUNDRY_COMPONENT_PATH" in
        *.pkg)
            sudo installer -pkg "$foundry_source" -target /
            ;;
        *.zip)
            foundry_expanded="$TEMP_ROOT/foundry-local"
            mkdir -p "$foundry_expanded"
            ditto -x -k "$foundry_source" "$foundry_expanded"
            [[ -x "$foundry_expanded/bin/foundry" ]] || \
                die 'verified Foundry Local zip has no executable bin/foundry'
            [[ -x "$foundry_expanded/bin/foundrylocald" ]] || \
                die 'verified Foundry Local zip has no executable bin/foundrylocald'
            [[ ! -e "$FOUNDRY_ZIP_DEST" && ! -L "$FOUNDRY_ZIP_DEST" ]] || \
                die 'Foundry Local destination appeared after preflight; manual merge/removal is required'
            [[ ! -e "$FOUNDRY_BIN_LINK" && ! -L "$FOUNDRY_BIN_LINK" ]] || \
                die 'Foundry Local command link appeared after preflight; manual merge/removal is required'
            sudo mkdir -p '/usr/local/libexec/foundrylocal' '/usr/local/bin'
            sudo ditto "$foundry_expanded/bin" "$FOUNDRY_ZIP_DEST"
            sudo chmod 0755 "$FOUNDRY_ZIP_DEST/foundry" "$FOUNDRY_ZIP_DEST/foundrylocald"
            sudo ln -s "$FOUNDRY_ZIP_DEST/foundry" "$FOUNDRY_BIN_LINK"
            ;;
    esac
}

if [[ "$FOUNDRY_ACTION" == 'install' ]]; then
    install_foundry_runtime
fi
hash -r

install_model_cache() {
    local source_path="$1"
    local destination_path="$2"
    local parent_path="${2%/*}"
    local label="$3"

    [[ ! -e "$destination_path" && ! -L "$destination_path" ]] || \
        die "$label destination appeared after preflight; manual merge is required"
    assert_safe_destination_parent "$destination_path" "$label"
    mkdir -p "$parent_path"
    assert_safe_destination_parent "$destination_path" "$label"
    ditto "$source_path" "$destination_path"
}

if [[ "$OLLAMA_MODEL_ACTION" == 'install' ]]; then
    install_model_cache "$SOURCE_ROOT/$OLLAMA_MODEL_COMPONENT_PATH" \
        "$OLLAMA_MODELS_DEST" 'Ollama model cache'
fi
if [[ "$FOUNDRY_MODEL_ACTION" == 'install' ]]; then
    install_model_cache "$SOURCE_ROOT/$FOUNDRY_MODEL_COMPONENT_PATH" \
        "$FOUNDRY_MODELS_DEST" 'Foundry Local model cache'
fi

install_config_file() {
    local source_path="$1"
    local destination_path="$2"
    local parent_path="${2%/*}"
    local label="$3"

    [[ ! -e "$destination_path" && ! -L "$destination_path" ]] || \
        die "$label destination appeared after preflight; manual merge is required"
    assert_safe_destination_parent "$destination_path" "$label"
    mkdir -p "$parent_path"
    assert_safe_destination_parent "$destination_path" "$label"
    ditto "$source_path" "$destination_path"
}

install_configs() {
    if [[ "$CHAT_CONFIG_ACTION" == 'install' ]]; then
        install_config_file "$CHAT_CONFIG_SOURCE" "$CHAT_CONFIG_DEST" 'chatLanguageModels.json'
    fi
    if [[ "$SETTINGS_CONFIG_ACTION" == 'install' ]]; then
        install_config_file "$SETTINGS_CONFIG_SOURCE" "$SETTINGS_CONFIG_DEST" 'VS Code settings.json'
    fi
    if [[ "$OLLAMA_CONFIG_ACTION" == 'install' ]]; then
        install_config_file "$OLLAMA_CONFIG_SOURCE" "$OLLAMA_CONFIG_DEST" 'Ollama server.json'
    fi
}

install_configs

if ! manifest_subtree_matches "$OLLAMA_MODEL_COMPONENT_PATH" "$OLLAMA_MODELS_DEST"; then
    die 'Ollama model cache does not match verified manifest hashes after placement'
fi
if [[ -n "$FOUNDRY_MODEL_COMPONENT_PATH" ]] && \
   ! manifest_subtree_matches "$FOUNDRY_MODEL_COMPONENT_PATH" "$FOUNDRY_MODELS_DEST"
then
    die 'Foundry Local model cache does not match verified manifest hashes after placement'
fi

cmp -s "$CHAT_CONFIG_SOURCE" "$CHAT_CONFIG_DEST" || die 'chatLanguageModels.json verification failed'
cmp -s "$SETTINGS_CONFIG_SOURCE" "$SETTINGS_CONFIG_DEST" || die 'VS Code settings.json verification failed'
cmp -s "$OLLAMA_CONFIG_SOURCE" "$OLLAMA_CONFIG_DEST" || die 'Ollama server.json verification failed'

if [[ "$CONTEXT_ACTION" == 'set' ]]; then
    launchctl setenv OLLAMA_CONTEXT_LENGTH "$CONTEXT_LENGTH"
fi

if [[ "$PYTHON_ACTION" == 'install' ]]; then
    [[ -x "$PYTHON_PACKAGE_BIN" ]] || die 'installed Python package did not provide its expected python3'
    PYTHON_BIN="$PYTHON_PACKAGE_BIN"
else
    PYTHON_BIN="$PYTHON_EXISTING_PATH"
fi
runtime_version "$PYTHON_BIN" 'installed Python'
[[ "$RUNTIME_VERSION" == "$PYTHON_VERSION" ]] || \
    die 'installed Python version does not match the manifest component version'

existing_app_version "$VSCODE_APP" 'installed VS Code'
[[ "$APP_VERSION" == "$VSCODE_VERSION" ]] || \
    die 'installed VS Code version does not match the manifest component version'
existing_app_version "$OLLAMA_APP" 'installed Ollama'
[[ "$APP_VERSION" == "$OLLAMA_VERSION" ]] || \
    die 'installed Ollama version does not match the manifest component version'

if [[ -n "$FOUNDRY_COMPONENT_PATH" ]]; then
    if [[ -x "$FOUNDRY_BIN_LINK" ]]; then
        FOUNDRY_BIN="$FOUNDRY_BIN_LINK"
    elif FOUNDRY_BIN="$(command -v foundry 2>/dev/null)"; then
        :
    else
        die 'Foundry Local was selected but the installed foundry command is unavailable'
    fi
    runtime_version "$FOUNDRY_BIN" 'installed Foundry Local'
    [[ "$RUNTIME_VERSION" == "$FOUNDRY_VERSION" ]] || \
        die 'installed Foundry Local version does not match the manifest component version'
fi

open -a Ollama || die 'failed to launch /Applications/Ollama.app'

OLLAMA_READY=0
OLLAMA_WAIT_ATTEMPT=0
while [[ "$OLLAMA_WAIT_ATTEMPT" -lt 60 ]]; do
    if curl --fail --silent --show-error --noproxy '*' \
        --connect-timeout 2 --max-time 5 "$OLLAMA_URL/api/tags" >/dev/null 2>&1
    then
        OLLAMA_READY=1
        break
    fi
    OLLAMA_WAIT_ATTEMPT=$((OLLAMA_WAIT_ATTEMPT + 1))
    sleep 1
done
[[ "$OLLAMA_READY" -eq 1 ]] || die 'Ollama loopback endpoint did not become ready within 60 attempts'

VERIFY_OUTPUT=''
VERIFY_STATUS=0
if VERIFY_OUTPUT="$("$PYTHON_BIN" "$VERIFY_SCRIPT" \
    --url "$OLLAMA_URL" \
    --model "$MODEL_NAME" \
    --timeout 600 \
    --require-agent \
    --expected-context "$CONTEXT_LENGTH" 2>&1)"
then
    VERIFY_STATUS=0
else
    VERIFY_STATUS=$?
    printf '%s\n' "$VERIFY_OUTPUT" >&2
    die_status "$VERIFY_STATUS" 'verify_endpoint.py --require-agent failed'
fi
printf '%s\n' "$VERIFY_OUTPUT"
case "$VERIFY_OUTPUT" in
    *'[ WARN ]'*) die 'verify_endpoint.py returned a warning; Agent verification is fail-closed' ;;
esac
if ! printf '%s\n' "$VERIFY_OUTPUT" | grep -Fq '結果: すべて OK'; then
    die 'verify_endpoint.py did not report an unqualified Agent success'
fi

printf '\nInstallation and automated Agent endpoint verification completed successfully.\n'
printf 'Manual completion check: verify the VS Code model picker, Chat, and Agent round trips.\n'