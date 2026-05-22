"""hve.gui.explorer_roots — エクスプローラー（FileTreePanel）監視ルートの解決と作成。

責務:
    - settings_store の ``options.explorer_roots``（";" 区切り文字列）を ``List[Path]`` に
      パースする。
    - 未存在のディレクトリは ``mkdir(parents=True, exist_ok=True)`` で作成する。
      ``.gitkeep`` 等のプレースホルダは作成しない（捏造禁止・最小限）。
    - リポジトリ相対 POSIX パスを ``repo_root`` 起点で絶対化する。空白要素は無視する。
      絶対パスが与えられた場合はそのまま採用する。
    - 重複は順序保存で除去する。

捏造禁止: 設定が空文字列の場合は空リストを返し、呼び出し側で fallback を決める。
本モジュールは「設定値の解決」のみを行い、既定値は ``settings_store.defaults()`` 側で持つ。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional


def _iter_tokens(raw: str) -> Iterable[str]:
    for token in (raw or "").split(";"):
        t = token.strip()
        if t:
            yield t


def parse_roots(raw: str, *, repo_root: Path) -> List[Path]:
    """";" 区切り文字列を絶対 ``Path`` リストに変換する（重複排除、作成は行わない）。"""
    seen: set[str] = set()
    out: List[Path] = []
    for token in _iter_tokens(raw):
        p = Path(token)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        else:
            p = p.resolve()
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def ensure_roots(paths: Iterable[Path]) -> List[Path]:
    """与えられたパス群に対し、未存在なら ``mkdir(parents=True, exist_ok=True)`` する。

    既にファイルとして存在するパスは作成せずそのまま返す（呼び出し側で扱う）。
    OSError は再送出せず無視し、呼び出し側がディレクトリ実在を別途確認できるよう
    入力パスをそのまま返す。
    """
    out: List[Path] = []
    for p in paths:
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError:
                # 作成失敗（権限・ファイル衝突等）はサイレントに継続。
                pass
        out.append(p)
    return out


def resolve_explorer_roots(
    raw: str,
    *,
    repo_root: Path,
    extra_roots: Optional[Iterable[Path]] = None,
) -> List[Path]:
    """設定値からエクスプローラー監視ルートを解決し、未存在ディレクトリを作成する。

    Args:
        raw: ``settings_store.get_option("explorer_roots")`` の値（";" 区切り）。
        repo_root: リポジトリルート。相対パスの起点。
        extra_roots: 設定値より前に並べたいルート（例: GUI セッション work_root）。
            ``None`` の場合は無視。重複は除去される。

    Returns:
        絶対パスのリスト。実ディレクトリ（``is_dir()`` が真）のみを返す。
    """
    bases: List[Path] = []
    seen: set[str] = set()

    # extra_roots は通常呼び出し側で既に作成済み（例: session_workdir.work_root）。
    # 念のため ensure_roots を通すため bases に含めるが、二重 mkdir 自体は
    # exist_ok=True により無害。
    if extra_roots is not None:
        for p in extra_roots:
            pa = Path(p).resolve()
            if str(pa) not in seen:
                seen.add(str(pa))
                bases.append(pa)

    for p in parse_roots(raw, repo_root=repo_root):
        if str(p) not in seen:
            seen.add(str(p))
            bases.append(p)

    ensure_roots(bases)

    # mkdir 後でもファイル名衝突等で is_dir() が偽になり得る。実ディレクトリのみ採用。
    return [p for p in bases if p.is_dir()]
