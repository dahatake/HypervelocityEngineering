#!/usr/bin/env bash
set -eu

: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${RUNNER_OS:?RUNNER_OS is required}"
: "${HVE_RUNNER_LABEL:?HVE_RUNNER_LABEL is required}"
: "${HVE_SOURCE_REF:?HVE_SOURCE_REF is required}"

[ "$(uname -s)" = "Darwin" ]
[ "$RUNNER_OS" = "macOS" ]
[ "$(uname -m)" = "arm64" ]
printf '%s' "$HVE_SOURCE_REF" | /usr/bin/grep -Eq '^[0-9a-f]{40}$'
SOURCE_COMMIT="$(git rev-parse HEAD)"
[ "$SOURCE_COMMIT" = "$HVE_SOURCE_REF" ]

case "$HVE_RUNNER_LABEL" in
  macos-15) EXPECTED_MAJOR=15 ;;
  macos-26) EXPECTED_MAJOR=26 ;;
  *) exit 2 ;;
esac

OS_VERSION="$(sw_vers -productVersion)"
OS_MAJOR="${OS_VERSION%%.*}"
[ "$OS_MAJOR" = "$EXPECTED_MAJOR" ]

ARTIFACT_DIR="$RUNNER_TEMP/hve-bootstrap-prerequisites"
OUTPUT="$ARTIFACT_DIR/runner-facts.txt"
mkdir -p "$ARTIFACT_DIR"

BREW_PATH=""
if [ -x /opt/homebrew/bin/brew ]; then
  BREW_PATH=/opt/homebrew/bin/brew
elif command -v brew >/dev/null 2>&1; then
  BREW_PATH="$(command -v brew)"
fi

{
  printf 'probe_status=facts-collected\n'
  printf 'source_commit=%s\n' "$SOURCE_COMMIT"
  printf 'runner_label=%s\n' "$HVE_RUNNER_LABEL"
  printf 'runner_os=%s\n' "$RUNNER_OS"
  printf 'image_os=%s\n' "${ImageOS:-unavailable}"
  printf 'image_version=%s\n' "${ImageVersion:-unavailable}"
  printf 'os=%s\n' "$OS_VERSION"
  printf 'architecture=arm64\n'
  printf 'xcode_select=%s\n' "$(xcode-select -p 2>/dev/null || true)"
  printf 'brew=%s\n' "$BREW_PATH"
  for command_name in python3 git gh node pwsh az shellcheck; do
    command_path="$(command -v "$command_name" 2>/dev/null || true)"
    printf '%s_available=%s\n' "$command_name" "$([ -n "$command_path" ] && printf true || printf false)"
    printf '%s_path=%s\n' "$command_name" "$command_path"
  done
} > "$OUTPUT"

test -s "$OUTPUT"
