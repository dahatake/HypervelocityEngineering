#!/usr/bin/env bash
set -u

CHECK_ONLY=false
WITH_WORKIQ=false
WITH_GUI=false
NO_GUI=false
WITH_SKILLS=false
INSTALL_EXTERNAL_COPILOT_CLI=false
FORCE=false
SKIP_MDQ=false
SKIP_MDQ_WATCH=false
WARNING_COUNT=0
GH_AUTH_OK=false

usage() {
  cat <<'USAGE'
Usage: ./hve/setup-hve.sh [options]

Options:
  --check-only                    Report current state without changing files.
  --with-workiq                   Check Node.js/npm/npx prerequisites for Work IQ.
  --with-gui                      Install GUI Orchestrator extras ([gui,gui-docconvert]) including PySide6 and markitdown.
  --no-gui                        With --force, exclude GUI extras (CLI-only setup).
  --with-skills                   Install externally-sourced agent skills (microsoft/skills) via npx into .github/skills/azure-skills/ (gitignored). Requires Node.js / npx.
  --install-external-copilot-cli  Install/check external copilot CLI when needed (uses Homebrew if available).
  --force                         Idempotent full rebuild: unconditionally delete .venv, recreate, install all required + GUI extras (unless --no-gui). Extras install failures become errors. Non-interactive (no prompt).
  --skip-mdq                      Skip installing markdown-query optional extras ([mdq]).
  --skip-mdq-watch                Install [mdq] but skip watcher extras (watchdog). HVE CLI Orchestrator realtime index update will be disabled.
  -h, --help                      Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=true ;;
    --with-workiq) WITH_WORKIQ=true ;;
    --with-gui) WITH_GUI=true ;;
    --no-gui) NO_GUI=true ;;
    --with-skills) WITH_SKILLS=true ;;
    --install-external-copilot-cli) INSTALL_EXTERNAL_COPILOT_CLI=true ;;
    --force) FORCE=true ;;
    --skip-mdq) SKIP_MDQ=true ;;
    --skip-mdq-watch) SKIP_MDQ_WATCH=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

# --force: 冪等な完全再構築。GUI extras を既定で含める（--no-gui で除外可）。
# extras 失敗は ERROR として扱い、追加タスク無しで hve/gui/cli 起動を保証。
if [[ "$FORCE" == true && "$NO_GUI" != true ]]; then
  WITH_GUI=true
fi

step() { printf '\n==> %s\n' "$1"; }
warn() { WARNING_COUNT=$((WARNING_COUNT + 1)); printf 'WARNING: %s\n' "$1" >&2; }
die() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

run() {
  printf '> '
  printf '%q ' "$@"
  printf '\n'
  "$@" || die "Command failed: $*"
}

python_info() {
  "$1" -c 'import sys; print(sys.executable); print(f"{sys.version_info.major} {sys.version_info.minor} {sys.version_info.micro}")' 2>/dev/null
}

python_is_311_or_newer() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

find_python311() {
  local candidate
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_311_or_newer "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"

cd "$REPO_ROOT" || exit 1

step "Checking required tools"
if command -v git >/dev/null 2>&1; then
  printf 'Git: %s\n' "$(command -v git)"
else
  warn "Git was not found. Install on a clean OS:
    macOS:        brew install git
    Ubuntu/Debian:sudo apt-get update && sudo apt-get install -y git
    Fedora/RHEL:  sudo dnf install -y git"
fi

if command -v gh >/dev/null 2>&1; then
  printf 'GitHub CLI: %s\n' "$(command -v gh)"
else
  warn "GitHub CLI was not found. Install on a clean OS:
    macOS:        brew install gh
    Ubuntu/Debian:see https://github.com/cli/cli/blob/trunk/docs/install_linux.md
    Fedora/RHEL:  sudo dnf install -y gh"
fi

PYTHON_BIN=""
if PYTHON_BIN="$(find_python311)"; then
  readarray -t PY_INFO < <(python_info "$PYTHON_BIN")
  printf 'Python: %s (%s)\n' "${PY_INFO[0]}" "${PY_INFO[1]}"
else
  warn "Python 3.11+ was not found. Install on a clean OS:
    macOS:        brew install python@3.13
    Ubuntu/Debian:sudo apt-get install -y python3.13 python3.13-venv  (24.04+)
    Fedora/RHEL:  sudo dnf install -y python3.13
    Other:        https://www.python.org/downloads/"
  if [[ "$CHECK_ONLY" != true ]]; then exit 1; fi
fi

# Linux: GUI (QtWebEngine) に必要な system lib を案内（自動インストールはしない）。
if [[ "$WITH_GUI" == true ]] && [[ "$(uname -s)" == "Linux" ]]; then
  step "Linux GUI system library check (informational)"
  missing_libs=""
  for lib in libxcb-cursor0 libnss3 libxkbcommon-x11-0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2; do
    if ! ldconfig -p 2>/dev/null | grep -q "${lib%-*}"; then
      missing_libs="${missing_libs} ${lib}"
    fi
  done
  if [[ -n "$missing_libs" ]]; then
    warn "Possibly missing system libs for Qt/QtWebEngine:${missing_libs}
    Ubuntu/Debian: sudo apt-get install -y${missing_libs}
    Fedora/RHEL:   use 'dnf provides' to map .so names to packages.
    Headless Linux (no X11/Wayland) cannot launch the GUI; use the CLI orchestrator."
  fi
fi

if [[ "$WITH_WORKIQ" == true ]]; then
  step "Checking Work IQ prerequisites"
  for tool in node npm npx; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf '%s: %s\n' "$tool" "$(command -v "$tool")"
    else
      warn "$tool was not found. Work IQ requires Node.js/npm/npx."
    fi
  done
  printf 'Work IQ may require Microsoft 365 sign-in, EULA acceptance, and Entra ID admin consent.\n'
fi

if [[ "$INSTALL_EXTERNAL_COPILOT_CLI" == true ]]; then
  step "Checking external Copilot CLI"
  if command -v copilot >/dev/null 2>&1; then
    printf 'External Copilot CLI: %s\n' "$(command -v copilot)"
  elif [[ "$CHECK_ONLY" == true ]]; then
    warn "External Copilot CLI was not found. It is optional unless COPILOT_CLI_PATH or --cli-path is used."
  elif command -v brew >/dev/null 2>&1; then
    run brew install copilot-cli
  else
    warn "Homebrew was not found. Install Copilot CLI manually from GitHub Docs."
  fi
fi

step "Checking Python virtual environment"
if [[ "$FORCE" == true && "$CHECK_ONLY" != true && -d "$VENV_DIR" ]]; then
  printf -- '--force specified: removing existing .venv at %s\n' "$VENV_DIR"
  rm -rf "$VENV_DIR"
fi
if [[ -x "$VENV_PYTHON" ]]; then
  if python_is_311_or_newer "$VENV_PYTHON"; then
    readarray -t VENV_INFO < <(python_info "$VENV_PYTHON")
    printf 'Existing .venv Python: %s\n' "${VENV_INFO[1]}"
  else
    warn "Existing .venv is older than Python 3.11. Rerun with --force to recreate it."
    if [[ "$CHECK_ONLY" != true ]]; then exit 1; fi
  fi
elif [[ "$CHECK_ONLY" == true ]]; then
  warn ".venv does not exist. Run without --check-only to create it."
fi

if [[ "$CHECK_ONLY" != true && ! -x "$VENV_PYTHON" ]]; then
  [[ -n "$PYTHON_BIN" ]] || die "Python 3.11+ is required to create .venv."
  run "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [[ -x "$VENV_PYTHON" ]]; then
  if [[ "$CHECK_ONLY" != true ]]; then
    step "Installing Python dependencies"
    run "$VENV_PYTHON" -m pip install --upgrade pip
    run "$VENV_PYTHON" -m pip install --upgrade github-copilot-sdk

    if [[ "$SKIP_MDQ" != true ]]; then
      if [[ "$SKIP_MDQ_WATCH" == true ]]; then BASE_EXTRAS="mdq"; else BASE_EXTRAS="mdq-watch"; fi
      # mdq-ja は Q5=A 採用上は空 extras（プレースホルダー）だが、今後形態素
      # 解析器を追加する際の拡張点として同梱しておく。
      EXTRAS_TARGET="${BASE_EXTRAS},mdq-ja"
      step "Installing markdown-query optional extras ([$EXTRAS_TARGET])"
      if "$VENV_PYTHON" -m pip install -e ".[$EXTRAS_TARGET]"; then
        printf '[%s] extras installed.\n' "$EXTRAS_TARGET"
      else
        if [[ "$FORCE" == true ]]; then
          die "Failed to install [$EXTRAS_TARGET] extras (--force)."
        fi
        warn "Failed to install [$EXTRAS_TARGET] extras. markdown-query Skill will still work with built-in fallback. Re-run later: $VENV_PYTHON -m pip install -e \".[$EXTRAS_TARGET]\""
      fi
      # FTS5 trigram tokenizer (ja-jp 用) のサポート確認。
      if "$VENV_PYTHON" -c "import sqlite3,sys; c=sqlite3.connect(':memory:');
try:
  c.execute(\"CREATE VIRTUAL TABLE p USING fts5(x,tokenize='trigram')\"); sys.exit(0)
except Exception:
  sys.exit(1)" >/dev/null 2>&1; then
        printf 'FTS5 trigram tokenizer (ja-jp 用): OK\n'
      else
        warn "FTS5 trigram tokenizer が未サポートです。SQLite 3.34+ を推奨。フォールバックとして unicode61 が使用されます。"
      fi
    fi

    if [[ "$WITH_GUI" == true ]]; then
      step "Installing GUI Orchestrator extras ([gui,gui-docconvert]) including markitdown"
      if "$VENV_PYTHON" -m pip install -e ".[gui,gui-docconvert]"; then
        printf '[gui,gui-docconvert] extras installed (PySide6 + markitdown[all]).\n'
        step "Downloading Mermaid / KaTeX assets for Markdown preview"
        if ! "$VENV_PYTHON" -m hve.gui.markdown_preview.download_assets; then
          warn "Asset download had failures. Markdown body will still render; Mermaid/KaTeX will be disabled."
        fi
      else
        if [[ "$FORCE" == true ]]; then
          die "Failed to install [gui,gui-docconvert] extras (--force)."
        fi
        warn "Failed to install [gui,gui-docconvert] extras. Re-run later: $VENV_PYTHON -m pip install -e \".[gui,gui-docconvert]\""
      fi
    fi
  fi

  step "Verifying HVE runtime"
  if "$VENV_PYTHON" -c 'import copilot' >/dev/null 2>&1; then
    printf 'github-copilot-sdk import: OK\n'
  else
    warn "github-copilot-sdk import failed. Run without --check-only to install dependencies."
  fi
  if "$VENV_PYTHON" -m hve --help >/dev/null 2>&1; then
    printf 'python -m hve --help: OK\n'
  else
    warn "python -m hve --help failed."
  fi

  if [[ "$SKIP_MDQ" != true ]]; then
    if "$VENV_PYTHON" -m mdq --help >/dev/null 2>&1; then
      printf 'python -m mdq --help: OK\n'
    else
      warn "python -m mdq --help failed. markdown-query Skill may not be available."
    fi
    if [[ "$CHECK_ONLY" == true ]]; then
      if "$VENV_PYTHON" -c 'import rank_bm25, tiktoken' >/dev/null 2>&1; then
        printf '[mdq] extras: OK (rank_bm25, tiktoken)\n'
      else
        warn "[mdq] extras missing. Run without --check-only to install, or pass --skip-mdq to suppress this check."
      fi
      if [[ "$SKIP_MDQ_WATCH" != true ]]; then
        if "$VENV_PYTHON" -c 'import watchdog' >/dev/null 2>&1; then
          printf '[mdq-watch] extras: OK (watchdog)\n'
        else
          warn "[mdq-watch] extras missing (watchdog). HVE CLI Orchestrator realtime index update will be disabled. Run without --check-only to install, or pass --skip-mdq-watch to suppress this check."
        fi
      fi
    fi
  fi

  if [[ "$WITH_GUI" == true && "$CHECK_ONLY" == true ]]; then
    if "$VENV_PYTHON" -c 'import PySide6' >/dev/null 2>&1; then
      printf '[gui] extras: OK (PySide6)\n'
    else
      warn "[gui] extras missing (PySide6). Run without --check-only to install."
    fi
    if "$VENV_PYTHON" -c 'import markitdown' >/dev/null 2>&1; then
      printf '[gui-docconvert] extras: OK (markitdown)\n'
    else
      warn "[gui-docconvert] extras missing (markitdown). Run without --check-only to install."
    fi
    if command -v pyside6-lupdate >/dev/null 2>&1; then
      printf 'pyside6-lupdate: OK (%s)\n' "$(command -v pyside6-lupdate)"
    else
      warn "pyside6-lupdate not found on PATH. GUI 多言語化リソース (.ts) の更新には PySide6 同梱の pyside6-lupdate / pyside6-lrelease が必要です。"
    fi
  fi

  # GUI 翻訳バイナリ (.qm) の自動生成
  if [[ "$WITH_GUI" == true && "$CHECK_ONLY" != true ]]; then
    TS_PATH="${REPO_ROOT}/hve/gui/i18n/hve_gui_en_US.ts"
    QM_PATH="${REPO_ROOT}/hve/gui/i18n/hve_gui_en_US.qm"
    if [[ -f "$TS_PATH" ]]; then
      NEED_BUILD=true
      if [[ -f "$QM_PATH" && "$QM_PATH" -nt "$TS_PATH" ]]; then
        NEED_BUILD=false
      fi
      if [[ "$NEED_BUILD" == true ]]; then
        if command -v pyside6-lrelease >/dev/null 2>&1; then
          step "Compiling GUI translations (hve_gui_en_US.ts -> .qm)"
          if pyside6-lrelease "$TS_PATH" -qm "$QM_PATH"; then
            printf 'GUI translations compiled: %s\n' "$QM_PATH"
          else
            warn "Failed to compile GUI translations. 英語表示にフォールバックする際は日本語のままになります。"
          fi
        else
          warn "pyside6-lrelease not found; skipping GUI translation compile. Run manually: pyside6-lrelease hve/gui/i18n/translations.pro"
        fi
      fi
    fi
  fi
fi

if command -v gh >/dev/null 2>&1; then
  step "Checking GitHub authentication"
  if gh auth status >/dev/null 2>&1; then
    GH_AUTH_OK=true
    printf 'gh auth status: OK\n'
  else
    warn "gh auth status failed. Run 'gh auth login' before using GitHub operations."
  fi
fi

if [[ "$WITH_SKILLS" == true && "$CHECK_ONLY" != true ]]; then
  step "Installing externally-sourced agent skills (microsoft/skills)"
  if ! command -v npx >/dev/null 2>&1; then
    warn "npx not found on PATH. Skipping skills install. Install Node.js 20+ first, then re-run: npx skills add microsoft/skills --skill '*' --agent copilot --yes --copy"
  else
    if npx -y skills add microsoft/skills --skill '*' --agent copilot --yes --copy; then
      printf 'microsoft/skills installed under .github/skills/azure-skills/ (gitignored).\n'
    else
      warn "Failed to install microsoft/skills. Re-run later: npx skills add microsoft/skills --skill '*' --agent copilot --yes --copy"
    fi
  fi
fi

step "Next steps"
if command -v gh >/dev/null 2>&1; then
  if [[ "$GH_AUTH_OK" == true ]]; then
    printf 'GitHub auth: OK (gh auth status)\n'
  else
    printf "Authenticate GitHub CLI if needed: gh auth login\n"
    printf "Then verify: gh auth status\n"
  fi
fi
if [[ -x "$VENV_PYTHON" ]]; then
  printf 'Basic runtime check: %s -m hve --help\n' "$VENV_PYTHON"
  if [[ "$SKIP_MDQ" != true ]]; then
    printf 'Markdown query (local): %s -m mdq index ; %s -m mdq stats\n' "$VENV_PYTHON" "$VENV_PYTHON"
    if [[ "$SKIP_MDQ_WATCH" != true ]]; then
      printf 'Markdown query (realtime, CLI Orchestrator only): watchdog installed. Disable with --no-mdq-watch or HVE_MDQ_WATCH=0.\n'
    fi
  fi
else
  printf 'Create .venv first (run setup without --check-only), then run: .venv/bin/python -m hve --help\n'
fi
printf 'Optional: Node.js / npm / npx are only required when using Work IQ or Node-based MCP tools.\n'
if [[ "$SKIP_MDQ" == true ]]; then
  printf 'markdown-query [mdq] extras skipped (--skip-mdq). Built-in fallback (MiniBM25) will be used.\n'
elif [[ "$SKIP_MDQ_WATCH" == true ]]; then
  printf 'markdown-query watcher extras skipped (--skip-mdq-watch). [mdq] installed but watchdog is not; HVE CLI Orchestrator realtime index update will be disabled.\n'
fi
if [[ "$WITH_GUI" == true ]]; then
  printf 'GUI Orchestrator: PySide6 + markitdown installed. Launch with: %s -m hve gui\n' "$VENV_PYTHON"
else
  printf 'GUI Orchestrator: skipped. To enable, re-run with --with-gui (installs PySide6 and markitdown for attachment Markdown conversion).\n'
fi

if [[ "$CHECK_ONLY" == true ]]; then
  printf '\nCheck-only completed with %s warning(s).\n' "$WARNING_COUNT"
else
  printf '\nHVE setup completed with %s warning(s).\n' "$WARNING_COUNT"
fi
