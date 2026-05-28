#!/usr/bin/env bash
# ============================================================
# hve/setup-hve.sh — HVE 完全セットアップ (Linux / macOS)
#
# 目的:
#   OS しか入っていない Linux / macOS から、HVE の CLI と GUI の
#   全機能を実行できる .venv をゼロから構築する。
#
# 既定で導入する extras (pyproject.toml と一致):
#   mdq-watch, mdq-ja, semantic, gui, gui-pty, gui-docconvert
#
# 行うこと:
#   - OS prereq 確認 (git / gh / python3.11+) と install hints
#   - Linux で Qt/QtWebEngine 必須 system lib の存在診断
#   - .venv 作成・検証
#   - pip / setuptools / wheel アップグレード
#   - editable install with extras
#   - github-copilot-sdk を最新化
#   - nltk punkt_tab を事前 DL
#   - Mermaid / KaTeX アセット DL
#   - GUI 翻訳 .ts → .qm コンパイル
#
# Usage:
#   ./hve/setup-hve.sh                既定: 全機能セットアップ
#   ./hve/setup-hve.sh --check-only   状態確認のみ
#   ./hve/setup-hve.sh --no-gui       GUI extras をスキップ
#   ./hve/setup-hve.sh --minimal      base のみ
#   ./hve/setup-hve.sh --force        .venv を再構築
#   ./hve/setup-hve.sh --skip-nltk-download
#   ./hve/setup-hve.sh --with-skills  microsoft/skills を npx で導入
# ============================================================
set -u

CHECK_ONLY=false
NO_GUI=false
MINIMAL=false
FORCE=false
SKIP_NLTK=false
WITH_SKILLS=false
ASSUME_YES=false
NO_INSTALL_PYTHON=false
WARN=0

usage() {
  sed -n '2,30p' "$0"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=true ;;
    --no-gui)     NO_GUI=true ;;
    --minimal)    MINIMAL=true ;;
    --force)      FORCE=true ;;
    --skip-nltk-download) SKIP_NLTK=true ;;
    --with-skills) WITH_SKILLS=true ;;
    -y|--yes)     ASSUME_YES=true ;;
    --no-install-python) NO_INSTALL_PYTHON=true ;;
    -h|--help)    usage ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
warn() { WARN=$((WARN+1)); printf '  [WARN] %s\n' "$1" >&2; }
die()  { printf '  [ERROR] %s\n' "$1" >&2; exit 1; }
run()  { printf '  > %s\n' "$*"; "$@" || die "Command failed: $*"; }

probe() { "$@" >/dev/null 2>&1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
VENV_PY="$VENV_DIR/bin/python"

cd "$REPO_ROOT"

INSTALL_GUI=true
[[ "$NO_GUI" == true ]] && INSTALL_GUI=false
[[ "$MINIMAL" == true ]] && INSTALL_GUI=false

OS="$(uname -s)"
echo "HVE setup ($OS)"
echo "  check-only=$CHECK_ONLY no-gui=$NO_GUI minimal=$MINIMAL force=$FORCE"
echo "  repoRoot=$REPO_ROOT"

# ---------- OS tool checks ----------
step 'Checking required OS tools'

if command -v git >/dev/null 2>&1; then ok "git: $(command -v git)"
else
  warn "git not found. Install:
    macOS:        brew install git
    Ubuntu/Debian:sudo apt-get update && sudo apt-get install -y git
    Fedora/RHEL:  sudo dnf install -y git"
fi

if command -v gh >/dev/null 2>&1; then ok "gh : $(command -v gh)"
else
  warn "GitHub CLI not found. Install:
    macOS:        brew install gh
    Ubuntu/Debian:see https://github.com/cli/cli/blob/trunk/docs/install_linux.md
    Fedora/RHEL:  sudo dnf install -y gh"
fi

find_python() {
  for c in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then
        echo "$c"
        return 0
      fi
    fi
  done
  return 1
}

confirm() {
  # $1 = prompt; returns 0 if yes
  if [[ "$ASSUME_YES" == true ]]; then return 0; fi
  if [[ ! -t 0 ]]; then return 1; fi  # non-interactive: refuse
  read -r -p "$1 [y/N]: " ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

detect_linux_pm() {
  if command -v apt-get >/dev/null 2>&1; then echo apt; return; fi
  if command -v dnf      >/dev/null 2>&1; then echo dnf; return; fi
  if command -v pacman   >/dev/null 2>&1; then echo pacman; return; fi
  echo unknown
}

install_python_auto() {
  # Attempts to install latest Python (3.14) using the OS-native package manager.
  # Returns 0 on success, 1 on failure / declined.
  local os pm
  os="$(uname -s)"
  case "$os" in
    Darwin)
      if ! command -v brew >/dev/null 2>&1; then
        warn 'Homebrew not found. Install from https://brew.sh/ then re-run this script.'
        return 1
      fi
      if confirm 'Install Python 3.14 via Homebrew? (no sudo required)'; then
        run brew update
        run brew install python@3.14 || return 1
        # link so python3.14 is on PATH
        brew link --overwrite --force python@3.14 >/dev/null 2>&1 || true
        return 0
      fi
      return 1
      ;;
    Linux)
      pm="$(detect_linux_pm)"
      case "$pm" in
        apt)
          if confirm 'Install Python 3.14 via apt (deadsnakes PPA, requires sudo)?'; then
            run sudo apt-get update
            run sudo apt-get install -y software-properties-common
            run sudo add-apt-repository -y ppa:deadsnakes/ppa
            run sudo apt-get update
            run sudo apt-get install -y python3.14 python3.14-venv python3.14-distutils || return 1
            return 0
          fi
          return 1
          ;;
        dnf)
          if confirm 'Install Python 3.14 via dnf (requires sudo)?'; then
            run sudo dnf install -y python3.14 || return 1
            return 0
          fi
          return 1
          ;;
        pacman)
          if confirm 'Install Python via pacman (requires sudo)?'; then
            run sudo pacman -Sy --noconfirm python || return 1
            return 0
          fi
          return 1
          ;;
        *)
          warn "Unknown Linux package manager. Install Python 3.14 manually from https://www.python.org/downloads/"
          return 1
          ;;
      esac
      ;;
    *)
      warn "Unsupported OS for auto-install: $os"
      return 1
      ;;
  esac
}

if PYBIN="$(find_python)"; then
  PYVER="$("$PYBIN" -c 'import sys;v=sys.version_info;print(f"{v[0]}.{v[1]}.{v[2]}")')"
  ok "Python 3.11+: $PYBIN ($PYVER)"
else
  printf '  [WARN] Python 3.11+ not found.\n'
  if [[ "$NO_INSTALL_PYTHON" != true && "$CHECK_ONLY" != true ]]; then
    if install_python_auto; then
      if PYBIN="$(find_python)"; then
        PYVER="$("$PYBIN" -c 'import sys;v=sys.version_info;print(f"{v[0]}.{v[1]}.{v[2]}")')"
        ok "Python 3.11+ installed: $PYBIN ($PYVER)"
      else
        die 'Python install reported success but no compatible interpreter found on PATH.'
      fi
    else
      printf '  [ERROR] Python 3.11+ not installed. Manual install (latest 3.14 recommended):\n'
      printf '    macOS:        brew install python@3.14\n'
      printf '    Ubuntu/Debian: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt-get update && sudo apt-get install -y python3.14 python3.14-venv\n'
      printf '    Fedora/RHEL:  sudo dnf install -y python3.14\n'
      printf '    Other:        https://www.python.org/downloads/\n'
      exit 1
    fi
  else
    printf '  [ERROR] Python 3.11+ not found. Install (latest 3.14 recommended):\n'
    printf '    macOS:        brew install python@3.14\n'
    printf '    Ubuntu/Debian: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt-get update && sudo apt-get install -y python3.14 python3.14-venv\n'
    printf '    Fedora/RHEL:  sudo dnf install -y python3.14\n'
    printf '    Other:        https://www.python.org/downloads/\n'
    [[ "$CHECK_ONLY" == true ]] || exit 1
  fi
fi

# Linux GUI system libs (informational)
if [[ "$INSTALL_GUI" == true && "$OS" == "Linux" ]]; then
  step 'Linux Qt/QtWebEngine system libraries (informational)'
  missing=""
  for lib in libxcb-cursor0 libnss3 libxkbcommon-x11-0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libegl1 libgl1; do
    short="${lib%-*}"
    if ! ldconfig -p 2>/dev/null | grep -q "$short"; then
      missing="$missing $lib"
    fi
  done
  if [[ -n "$missing" ]]; then
    warn "Possibly missing Qt/QtWebEngine system libs:$missing
    Ubuntu/Debian: sudo apt-get install -y$missing
    Fedora/RHEL:   use 'dnf provides' to map .so names to packages.
    Headless Linux (no X11/Wayland) cannot launch GUI; use CLI orchestrator."
  else
    ok 'Qt system libs look present'
  fi
fi

# ---------- venv ----------
step 'Preparing .venv'
if [[ "$FORCE" == true && "$CHECK_ONLY" != true && -d "$VENV_DIR" ]]; then
  echo "  --force: removing existing .venv"
  rm -rf "$VENV_DIR"
fi
if [[ -x "$VENV_PY" ]]; then
  if "$VENV_PY" -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then
    ok ".venv exists and is Python 3.11+"
  else
    if [[ "$CHECK_ONLY" == true ]]; then
      warn "Existing .venv is older than Python 3.11. Re-run with --force."
    else
      echo "  Existing .venv is older than Python 3.11. Recreating."
      rm -rf "$VENV_DIR"
    fi
  fi
fi
if [[ ! -x "$VENV_PY" && "$CHECK_ONLY" != true ]]; then
  [[ -n "${PYBIN:-}" ]] || die "Python 3.11+ is required to create .venv."
  run "$PYBIN" -m venv "$VENV_DIR"
  ok ".venv created"
fi

if [[ "$CHECK_ONLY" == true ]]; then
  [[ -x "$VENV_PY" ]] || warn ".venv does not exist. Run without --check-only."
  printf '\nCheck-only completed with %s warning(s).\n' "$WARN"
  exit 0
fi

# ---------- pip upgrade ----------
step 'Upgrading pip / setuptools / wheel'
run "$VENV_PY" -m pip install --upgrade pip setuptools wheel

# ---------- editable install with extras ----------
if [[ "$MINIMAL" == true ]]; then
  step 'Installing HVE (base only, no extras)'
  run "$VENV_PY" -m pip install -e .
else
  extras="mdq-watch,mdq-ja,semantic"
  if [[ "$INSTALL_GUI" == true ]]; then
    extras="$extras,gui,gui-pty,gui-docconvert"
  fi
  step "Installing HVE with extras: [$extras]"
  run "$VENV_PY" -m pip install -e ".[$extras]"
fi

# ---------- copilot SDK 最新化 ----------
# NOTE: --no-deps を付与し SDK 本体のみ更新する。これを付けないと pip resolver が
#   pydantic-core を最新版 (例: 2.47.0) へ引き上げ、pydantic 2.13.4 が要求する
#   pin (pydantic-core==2.46.4) と不整合になり GUI 起動時に例外となる。
#   SDK の依存 (pydantic>=2.0 等) は editable install 時点で既に充足済み。
step 'Upgrading github-copilot-sdk to latest (no-deps)'
run "$VENV_PY" -m pip install --upgrade --no-deps github-copilot-sdk

# ---------- 依存整合性チェック（pydantic / pydantic-core 等） ----------
# github-copilot-sdk の --upgrade 時に pip resolver が pydantic-core を
# 最新版 (例: 2.47.0) へ引き上げてしまい、pydantic 本体が要求する
# pin (例: pydantic 2.13.4 → pydantic-core==2.46.4) と不整合になるケースを
# 自動修復する。`pip check` が NG なら pydantic を force-reinstall して
# 正しい pydantic-core を再導入する。
step 'Verifying dependency consistency (pip check)'
if ! "$VENV_PY" -m pip check >/dev/null 2>&1; then
  warn 'pip check detected inconsistencies. Reinstalling pydantic to re-pin pydantic-core.'
  run "$VENV_PY" -m pip install --upgrade --force-reinstall pydantic
fi

# ---------- nltk punkt_tab ----------
if [[ "$MINIMAL" != true && "$SKIP_NLTK" != true ]]; then
  step 'Pre-downloading nltk punkt_tab (semantic_paragraph)'
  # 失敗時の原因を可視化するため quiet=False + 1回リトライ。stderr は表示。
  if "$VENV_PY" -c '
import nltk, sys, time
last = None
for i in range(2):
    try:
        if nltk.download("punkt_tab", quiet=False, raise_on_error=True):
            sys.exit(0)
        last = "nltk.download returned False"
    except Exception as e:
        last = f"{type(e).__name__}: {e}"
        print(f"[retry {i+1}/2] {last}", file=sys.stderr)
        time.sleep(2)
print(f"[final] {last}", file=sys.stderr)
sys.exit(1)
'; then
    ok 'nltk punkt_tab downloaded'
  else
    warn 'nltk punkt_tab download failed (see error above). semantic_paragraph will fallback to regex split until network is available.'
  fi
fi

# ---------- Mermaid / KaTeX assets ----------
if [[ "$INSTALL_GUI" == true ]]; then
  step 'Downloading Mermaid / KaTeX assets for Markdown preview'
  if "$VENV_PY" -m hve.gui.markdown_preview.download_assets; then
    ok 'Mermaid / KaTeX assets ready'
  else
    warn 'Asset download failed. Markdown body will still render; Mermaid/KaTeX disabled.'
  fi
fi

# ---------- GUI .ts -> .qm ----------
if [[ "$INSTALL_GUI" == true ]]; then
  TS="$REPO_ROOT/hve/gui/i18n/hve_gui_en_US.ts"
  QM="$REPO_ROOT/hve/gui/i18n/hve_gui_en_US.qm"
  if [[ -f "$TS" ]]; then
    need_build=true
    if [[ -f "$QM" && "$QM" -nt "$TS" ]]; then need_build=false; fi
    if [[ "$need_build" == true ]]; then
      step 'Compiling GUI translations (.ts -> .qm)'
      LRELEASE="$VENV_DIR/bin/pyside6-lrelease"
      if [[ ! -x "$LRELEASE" ]] && command -v pyside6-lrelease >/dev/null 2>&1; then
        LRELEASE="$(command -v pyside6-lrelease)"
      fi
      if [[ -x "$LRELEASE" ]]; then
        if "$LRELEASE" "$TS" -qm "$QM"; then ok ".qm compiled: $QM"
        else warn "pyside6-lrelease failed"; fi
      else
        warn 'pyside6-lrelease not found in .venv. GUI may show Japanese fallback.'
      fi
    else
      ok '.qm is up-to-date'
    fi
  fi
fi

# ---------- microsoft/skills ----------
if [[ "$WITH_SKILLS" == true ]]; then
  step 'Installing microsoft/skills via npx'
  if ! command -v npx >/dev/null 2>&1; then
    warn 'npx not found. Install Node.js 20+ and re-run with --with-skills.'
  else
    if npx -y skills add microsoft/skills --skill '*' --agent copilot --yes --copy; then
      ok 'microsoft/skills installed'
    else
      warn 'microsoft/skills install failed'
    fi
  fi
fi

# ---------- verify ----------
step 'Verifying installation'

verify() { local name="$1"; shift; if "$VENV_PY" "$@" >/dev/null 2>&1; then ok "$name"; else warn "$name verification failed"; fi; }

verify 'hve --help'     -m hve --help
verify 'copilot import' -c 'import copilot'
if [[ "$MINIMAL" != true ]]; then
  verify 'mdq --help'   -m mdq --help
  verify 'rank_bm25'    -c 'import rank_bm25'
  verify 'tiktoken'     -c 'import tiktoken'
  verify 'watchdog'     -c 'import watchdog'
  verify 'fastembed'    -c 'import fastembed'
  verify 'nltk'         -c 'import nltk'
  verify 'numpy'        -c 'import numpy'
fi
if [[ "$INSTALL_GUI" == true ]]; then
  verify 'PySide6'              -c 'import PySide6'
  verify 'QtWebEngineWidgets'   -c 'import PySide6.QtWebEngineWidgets'
  verify 'markdown_it'          -c 'import markdown_it'
  verify 'mdit_py_plugins'      -c 'import mdit_py_plugins'
  verify 'pygments'             -c 'import pygments'
  verify 'markitdown'           -c 'import markitdown'
  verify 'ptyprocess'           -c 'import ptyprocess'
fi

# FTS5 trigram
if "$VENV_PY" - <<'PY' >/dev/null 2>&1
import sqlite3,sys
c=sqlite3.connect(':memory:')
try:
    c.execute("CREATE VIRTUAL TABLE p USING fts5(x,tokenize='trigram')")
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
then
  ok 'SQLite FTS5 trigram tokenizer (ja-jp)'
else
  warn 'SQLite < 3.34: FTS5 trigram unavailable. Falls back to unicode61.'
fi

if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then ok 'gh auth status'
  else warn 'gh not authenticated. Run: gh auth login'; fi
fi

step 'Next steps'
echo "  CLI : $VENV_PY -m hve --help     (or ./hve.sh --help)"
if [[ "$INSTALL_GUI" == true ]]; then
  echo "  GUI : $VENV_PY -m hve gui        (or ./hve.sh gui)"
fi
echo "  Activate venv: source $VENV_DIR/bin/activate"

printf '\nHVE setup completed with %s warning(s).\n' "$WARN"
exit 0
