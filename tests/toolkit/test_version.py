import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("bump_version", ROOT / "tools" / "bump-version.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_current_version_is_0_2_0():
    assert _load().current() == "0.2.0"


def test_bump_rules():
    bump = _load().bump
    assert bump("0.1.0", "patch") == "0.1.1"
    assert bump("0.1.3", "minor") == "0.2.0"
    assert bump("0.1.3", "major") == "1.0.0"
    assert bump("0.1.3", "2.0.1") == "2.0.1"


def test_install_version_flag():
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "install.py"), "--version"], capture_output=True, text=True)
    assert out.returncode == 0
    assert re.fullmatch(r"\d+\.\d+\.\d+", out.stdout.strip())
