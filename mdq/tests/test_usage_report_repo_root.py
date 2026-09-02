"""FR-KIT-04: 配布ラッパーは対象リポジトリの利用ログを集計する。

`generate_usage_report.py` は vendor を `sys.path` の先頭へ置くため、
既定のリポジトリ解決が vendor 自身を指すと、実際の `.mdq/usage.jsonl` を
読まないまま「0 件」のレポートを出力してしまう。
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "tools" / "skills" / "markdown_query" / "generate_usage_report.py"


def _wrapper_module():
    spec = importlib.util.spec_from_file_location("_mdq_usage_report_wrapper", WRAPPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_wrapper_default_repo_root_is_not_the_vendor_directory() -> None:
    module = _wrapper_module()
    resolved = Path(module.default_repo_root())
    assert resolved.name != "vendor"
    assert not (resolved / "mdq" / "usage_report.py").is_file() or resolved == REPO_ROOT


def test_wrapper_default_repo_root_holds_the_usage_log_location() -> None:
    """`.mdq/` を持つ（または持ちうる）リポジトリルートを指すこと。"""
    module = _wrapper_module()
    resolved = Path(module.default_repo_root())
    assert (resolved / "mdq.toml").is_file() or (resolved / ".mdq").is_dir()


def test_wrapper_reports_the_repository_usage_log(tmp_path: Path) -> None:
    module = _wrapper_module()
    (tmp_path / ".mdq").mkdir()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "search",
        "args": {"q": "x", "top_k": 5, "max_tokens": 800},
        "elapsed_ms": 1,
        "result": {"hit_count": 1, "snippet_chars": 10, "source_file_chars": 100},
        "exit_code": 0,
    }
    (tmp_path / ".mdq" / "usage.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths = module.generate_report(tmp_path, window_days=30)
    stats = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert stats["record_count"] == 1
