"""hve.gui.app_catalog_loader — `docs/catalog/app-arch-catalog.md` から
APP-ID と APP 名のリストを抽出するパーサ。

- §A サマリ表（先頭の `| APP-ID | APP名 | ...`）から (id, name) を抽出する。
- プロセス内キャッシュ（同一 repo_root に対し 1 回だけ読み込み）。
- ファイル不在・解析失敗時は空リストを返す（呼び出し側で「全て実行」と解釈）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class AppEntry:
    app_id: str
    name: str
    architecture: str = ""

    @property
    def display_label(self) -> str:
        return f"{self.app_id}: {self.name}" if self.name else self.app_id

    def display_label_with_kind(self, kind: str = "") -> str:
        """アーキタグ付きラベル。``kind`` が空文字なら従来の表示を返す。"""
        base = self.display_label
        return f"{base} [{kind}]" if kind else base


_CACHE: Dict[Path, List[AppEntry]] = {}

# 3 列目（推薦アーキテクチャ）まで任意で抽出する。3 列目がない catalog でも
# 後方互換のため app_id / name のみで AppEntry を生成可能。
_APP_ROW_RE = re.compile(
    r"^\|\s*(APP-\d+[A-Za-z0-9_-]*)\s*\|\s*([^|]+?)\s*\|(?:\s*([^|]*?)\s*\|)?"
)


def _catalog_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "catalog" / "app-arch-catalog.md"


def parse(text: str) -> List[AppEntry]:
    """Markdown 文字列から APP エントリを抽出する。

    §A サマリ表（最初に現れる `| APP-ID | APP名 | ...` 表）の行のみ採用する。
    重複する APP-ID は最初の出現を採用する。
    """
    entries: List[AppEntry] = []
    seen: set = set()
    in_table = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        # ヘッダ検出: 区切り行（|---|---|...）の直前直後で OK
        if "| APP-ID" in line and "APP名" in line:
            in_table = True
            continue
        if not in_table:
            continue
        # 表終了判定: 表外（空行 or 新セクション）
        if line.startswith("#") or not line.strip():
            in_table = False
            continue
        # 区切り行はスキップ
        if re.match(r"^\|[-:\s|]+\|\s*$", line):
            continue
        m = _APP_ROW_RE.match(line)
        if not m:
            continue
        app_id = m.group(1).strip()
        name = m.group(2).strip()
        arch = (m.group(3) or "").strip()
        if app_id in seen:
            continue
        seen.add(app_id)
        entries.append(AppEntry(app_id=app_id, name=name, architecture=arch))
    return entries


def load_app_entries(repo_root: Path, *, use_cache: bool = True) -> List[AppEntry]:
    """`docs/catalog/app-arch-catalog.md` から APP リストを取得する。

    Args:
        repo_root: リポジトリのルートディレクトリ。
        use_cache: True のときプロセス内キャッシュを利用する。
            False ならキャッシュをバイパスして再読込（テスト用）。

    Returns:
        AppEntry のリスト。ファイル不在・解析失敗時は空リスト。
    """
    repo_root = Path(repo_root)
    if use_cache and repo_root in _CACHE:
        return list(_CACHE[repo_root])
    path = _catalog_path(repo_root)
    if not path.exists():
        _CACHE[repo_root] = []
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _CACHE[repo_root] = []
        return []
    entries = parse(text)
    _CACHE[repo_root] = entries
    return list(entries)


def clear_cache(repo_root: Optional[Path] = None) -> None:
    """キャッシュをクリアする（テスト用）。"""
    if repo_root is None:
        _CACHE.clear()
    else:
        _CACHE.pop(Path(repo_root), None)
