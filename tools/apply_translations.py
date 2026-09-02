"""tools/apply_translations.py — TRANSLATIONS dict を .ts ファイルに適用する。

使い方:
  python tools/apply_translations.py <translations.py> <target.ts>

仕様:
  - ``<translations.py>`` から ``TRANSLATIONS: dict[str, str]`` をインポート
  - ``<target.ts>`` の各 ``<message>`` 内の ``<source>...</source>`` をキーで lookup
  - ヒットした場合 ``<translation type="unfinished"></translation>`` を
    ``<translation>...</translation>`` に置換
  - lookup 漏れは標準出力に件数とサンプルを表示
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


def _load_translations(py_path: Path) -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("_translations", py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "TRANSLATIONS")


_MESSAGE_RE = re.compile(
    r"(<message>.*?<source>(.*?)</source>.*?<translation)( type=\"unfinished\")?(>)(.*?)(</translation>.*?</message>)",
    re.DOTALL,
)


def apply(ts_path: Path, translations: dict[str, str]) -> tuple[int, int, list[str]]:
    content = ts_path.read_text(encoding="utf-8")
    applied = 0
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        nonlocal applied
        head = match.group(1)
        source = match.group(2)
        # group(3): ' type="unfinished"' or None
        gt = match.group(4)
        existing = match.group(5)
        tail = match.group(6)
        translated = translations.get(source)
        if translated is None or not translated:
            if not existing.strip():
                missing.append(source)
            return match.group(0)
        applied += 1
        # 削除: type="unfinished" 属性
        return f"{head}{gt}{translated}{tail}"

    new_content = _MESSAGE_RE.sub(_sub, content)
    ts_path.write_text(new_content, encoding="utf-8")
    total = len(_MESSAGE_RE.findall(content))
    return applied, total, missing


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: apply_translations.py <translations.py> <target.ts>", file=sys.stderr)
        return 2
    translations = _load_translations(Path(argv[0]))
    ts_path = Path(argv[1])
    applied, total, missing = apply(ts_path, translations)
    print(f"applied: {applied} / {total} messages")
    if missing:
        unique_missing = list(dict.fromkeys(missing))
        print(f"missing translations: {len(unique_missing)} unique (showing up to 10):")
        for s in unique_missing[:10]:
            print(f"  - {s!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
