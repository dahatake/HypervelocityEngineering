"""ASDW Step 1.3 launcher の Windows 実行時契約を固定する。

live canary (`20260728T034239-836daa`) の Wave 9 で Step 1.3 が失敗した後の
経路監査で、Azure CLI 解決以外に 3 件の Windows 固有欠陥が見つかった。

- (A) launcher が設計書 `.md` とサンプル `.json` の CRLF を拒否する。
      `.gitattributes` は `*.sh` にしか `eol=lf` を付けておらず、
      `core.autocrlf=true` の Windows では両ファイルが必ず CRLF になる。
      generator は同じ 2 ファイルを `allow_crlf=True` で読むため、
      generator と gate は通過して launcher だけが落ちる非対称があった。
- (B) 子プロセス環境が allowlist で完全置換され、Windows の home 変数が
      消えるため、bash 内の `az` が設定ディレクトリを相対パス `~/.azure`
      へ解決してログイン済みトークンを見失う（かつ cwd に `~` を作る）。
- (D) 信頼 Bash に Git の `bin/bash.exe` を使うと、注入した信頼 PATH より
      前に `/c/bin` 等が前置され、「継承 PATH を探索しない」保証が崩れる。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve import asdw_data_script_launcher as launcher  # noqa: E402


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


# --- (A) CRLF ---------------------------------------------------------------


def test_read_stable_utf8_file_normalizes_crlf_when_allowed(tmp_path: Path) -> None:
    target = _write(tmp_path / "design.md", b"# Title\r\nbody\r\n")

    snapshot = launcher._read_stable_utf8_file(
        target, tmp_path, "design", allow_crlf=True
    )

    assert snapshot.text == "# Title\nbody\n"
    assert "\r" not in snapshot.text


def test_read_stable_utf8_file_rejects_crlf_by_default(tmp_path: Path) -> None:
    target = _write(tmp_path / "producer.sh", b"#!/usr/bin/env bash\r\n")

    with pytest.raises(launcher.ScriptLauncherError):
        launcher._read_stable_utf8_file(target, tmp_path, "producer")


def test_read_stable_utf8_file_rejects_lone_cr_even_when_crlf_allowed(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path / "design.md", b"# Title\rbody\n")

    with pytest.raises(launcher.ScriptLauncherError):
        launcher._read_stable_utf8_file(target, tmp_path, "design", allow_crlf=True)


def test_stage_snapshots_accept_crlf_design_and_sample(tmp_path: Path) -> None:
    """Windows チェックアウトそのままの CRLF 入力で verify stage が読める。"""
    _write(tmp_path / launcher._DESIGN, b"# design\r\nprivate\r\n")
    _write(tmp_path / launcher._SAMPLE, b'{\r\n  "a": 1\r\n}\r\n')
    _write(tmp_path / launcher._VERIFY, b"#!/usr/bin/env bash\nset -euo pipefail\n")

    snapshots = launcher._stage_snapshots("verify", tmp_path)

    assert "\r" not in snapshots[launcher._DESIGN].text
    assert "\r" not in snapshots[launcher._SAMPLE].text
    assert snapshots[launcher._VERIFY].text.startswith("#!/usr/bin/env bash\n")


def test_stage_snapshots_still_reject_crlf_producers(tmp_path: Path) -> None:
    """生成物である `.sh` は LF 厳格のまま維持する。"""
    _write(tmp_path / launcher._DESIGN, b"# design\n")
    _write(tmp_path / launcher._SAMPLE, b"{}\n")
    _write(tmp_path / launcher._VERIFY, b"#!/usr/bin/env bash\r\n")

    with pytest.raises(launcher.ScriptLauncherError):
        launcher._stage_snapshots("verify", tmp_path)


# --- (B) 子プロセスの host runtime 変数 --------------------------------------


def test_child_environment_supplies_azure_config_dir_from_parent() -> None:
    """親が明示した Azure CLI 設定ディレクトリをそのまま引き継ぐ。"""
    child = launcher._build_child_environment(
        {
            "RESOURCE_GROUP": "example-rg",
            "DATA_NETWORK_MODE": "private",
            "AZURE_CONFIG_DIR": os.path.join("C:", os.sep, "azure-config"),
        },
        "prep",
    )

    assert child["AZURE_CONFIG_DIR"] == os.path.join("C:", os.sep, "azure-config")


@pytest.mark.skipif(os.name != "nt", reason="Windows の home 変数解決を固定する")
def test_child_environment_derives_azure_config_dir_from_userprofile() -> None:
    """`AZURE_CONFIG_DIR` 未設定でも `az` が既定の設定ディレクトリを見つける。"""
    child = launcher._build_child_environment(
        {
            "RESOURCE_GROUP": "example-rg",
            "DATA_NETWORK_MODE": "private",
            "USERPROFILE": r"C:\Users\example",
        },
        "prep",
    )

    assert child["USERPROFILE"] == r"C:\Users\example"
    assert child["AZURE_CONFIG_DIR"] == str(Path(r"C:\Users\example") / ".azure")


@pytest.mark.skipif(os.name != "nt", reason="Windows の一時ディレクトリ解決を固定する")
def test_child_environment_forwards_windows_temp_directories() -> None:
    """`TEMP`/`TMP` を落とすと子の一時領域が `C:\\WINDOWS\\Temp` に落ちる。"""
    child = launcher._build_child_environment(
        {
            "RESOURCE_GROUP": "example-rg",
            "DATA_NETWORK_MODE": "private",
            "TEMP": r"C:\Users\example\AppData\Local\Temp",
            "TMP": r"C:\Users\example\AppData\Local\Temp",
        },
        "prep",
    )

    assert child["TEMP"] == r"C:\Users\example\AppData\Local\Temp"
    assert child["TMP"] == r"C:\Users\example\AppData\Local\Temp"


def test_child_environment_still_drops_unrelated_parent_keys() -> None:
    """host runtime 変数の追加が allowlist の遮断を緩めていない。"""
    child = launcher._build_child_environment(
        {
            "RESOURCE_GROUP": "example-rg",
            "DATA_NETWORK_MODE": "private",
            "UNRELATED_SECRET": "must-not-reach-child",
            "AZURE_CLIENT_SECRET": "must-not-reach-child",
        },
        "prep",
    )

    assert "UNRELATED_SECRET" not in child
    assert "AZURE_CLIENT_SECRET" not in child


# --- MSYS 引数パス変換の抑止 -------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="MSYS の引数変換は Windows 固有")
def test_child_environment_disables_msys_argument_path_conversion() -> None:
    """ARM スコープ ID が Windows パスへ書き換えられるのを防ぐ。

    MSYS は POSIX 風の引数をネイティブ実行ファイルへ渡す前に Windows パスへ
    変換する。実測では `--scope "/subscriptions/<id>"` が
    `C:/Program Files/Git/subscriptions/<id>` に化け、Azure CLI が
    `Invalid value in --scope` で拒否した。各 stage がネイティブツールへ渡す
    パスは既に Windows 形式であり、変換は一切不要。
    """
    child = launcher._build_child_environment(
        {"RESOURCE_GROUP": "example-rg", "DATA_NETWORK_MODE": "private"},
        "prep",
    )

    assert child["MSYS_NO_PATHCONV"] == "1"
    assert child["MSYS2_ARG_CONV_EXCL"] == "*"


@pytest.mark.skipif(os.name != "nt", reason="MSYS の引数変換は Windows 固有")
def test_windows_script_dir_survives_disabled_path_conversion(tmp_path: Path) -> None:
    """変換抑止後も Windows 形式の SCRIPT_DIR が子 bash から解決できる。"""
    child = launcher._build_child_environment(
        {"RESOURCE_GROUP": "example-rg", "DATA_NETWORK_MODE": "private"},
        "prep",
    )
    child["HVE_ASDW_SCRIPT_DIR"] = str(tmp_path)

    completed = subprocess.run(
        [launcher._trusted_bash_path(), "--noprofile", "--norc", "-s"],
        env=child,
        cwd=str(tmp_path),
        input=b'test -d "$HVE_ASDW_SCRIPT_DIR" && echo DIR_OK\n',
        capture_output=True,
    )

    assert completed.returncode == 0
    assert b"DIR_OK" in completed.stdout


# --- (D) 信頼 Bash -----------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="Windows の Bash 選択を固定する")
def test_trusted_bash_path_avoids_the_git_wrapper_bin() -> None:
    """`Git/bin/bash.exe` は信頼 PATH より前に `/c/bin` 等を前置する。"""
    resolved = launcher._trusted_bash_path()

    assert Path(resolved).exists()
    assert Path(resolved).parent.name == "bin"
    assert Path(resolved).parent.parent.name == "usr", (
        f"継承 PATH を前置しない usr/bin の Bash を使うこと: {resolved}"
    )
