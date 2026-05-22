"""hve.gui.markdown_preview.markdown_loader — ファイルパスからプレビュー素材を読み込む。

責務:
    - 拡張子・サイズ・バイナリ判定により ``LoaderResult.kind`` を決定する。
    - テキストファイルは utf-8 → cp932 フォールバックで読み出す。
    - レンダリング自体は行わない（呼び出し側で renderer 振り分け）。

責務外（敵対的レビュー #15 で境界明示）:
    - Markdown → HTML 変換は ``MarkdownHtmlRenderer`` の役割。
    - シンタックスハイライト HTML 生成は ``CodeHighlighter`` の役割。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


# サイズ閾値（敵対的レビュー #18）。これを超えるファイルは ``oversize`` 扱い。
MAX_FILE_BYTES: int = 2 * 1024 * 1024  # 2 MB

# Markdown とみなす拡張子。
_MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd"}

# シンタックスハイライト対象とみなす拡張子（Pygments 対応の主要言語）。
_CODE_SUFFIXES = {
    ".py", ".pyi", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".ini",
    ".sh", ".bash", ".ps1", ".bat", ".cmd",
    ".html", ".htm", ".css", ".scss",
    ".java", ".kt", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".sql", ".xml",
}


class LoaderKind(Enum):
    """読み込み結果の種別。"""

    MARKDOWN = "markdown"
    CODE = "code"
    PLAIN = "plain"
    BINARY = "binary"
    OVERSIZE = "oversize"
    MISSING = "missing"
    ERROR = "error"


@dataclass(frozen=True)
class LoaderResult:
    """``MarkdownLoader.load()`` の戻り値。

    Attributes:
        path: 入力パス。
        kind: 種別。
        raw_text: テキスト内容（MARKDOWN / CODE / PLAIN のみ非 None）。
        size_bytes: ファイルサイズ（取得できない場合 None）。
        error: ERROR / MISSING / OVERSIZE / BINARY のとき表示するメッセージ。
    """

    path: Path
    kind: LoaderKind
    raw_text: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


def _looks_binary(sample: bytes) -> bool:
    """NUL バイトを含めばバイナリ判定。"""
    return b"\x00" in sample


class MarkdownLoader:
    """ファイル読み込みと種別判定を行う純粋ロジック。

    Args:
        max_bytes: oversize 判定の閾値。
    """

    def __init__(self, max_bytes: int = MAX_FILE_BYTES) -> None:
        self._max_bytes = max_bytes

    def load(self, path: Path) -> LoaderResult:
        p = Path(path)

        if not p.exists() or not p.is_file():
            return LoaderResult(
                path=p,
                kind=LoaderKind.MISSING,
                error=f"ファイルが見つかりません: {p}",
            )

        try:
            size = p.stat().st_size
        except OSError as exc:
            return LoaderResult(
                path=p,
                kind=LoaderKind.ERROR,
                error=f"ファイル情報の取得に失敗: {exc}",
            )

        if size > self._max_bytes:
            return LoaderResult(
                path=p,
                kind=LoaderKind.OVERSIZE,
                size_bytes=size,
                error=f"サイズ上限 {self._max_bytes // 1024 // 1024} MB を超えています ({size:,} bytes)",
            )

        # 先頭 4 KB でバイナリ判定
        try:
            with p.open("rb") as f:
                head = f.read(4096)
        except OSError as exc:
            return LoaderResult(
                path=p,
                kind=LoaderKind.ERROR,
                size_bytes=size,
                error=f"読み込みエラー: {exc}",
            )

        if _looks_binary(head):
            return LoaderResult(
                path=p,
                kind=LoaderKind.BINARY,
                size_bytes=size,
                error="バイナリファイルのため表示できません",
            )

        # テキスト読み込み (utf-8 → cp932 fallback)
        text: Optional[str] = None
        for enc in ("utf-8", "cp932"):
            try:
                text = p.read_text(encoding=enc)
                break
            except (UnicodeDecodeError, OSError):
                continue
        if text is None:
            return LoaderResult(
                path=p,
                kind=LoaderKind.ERROR,
                size_bytes=size,
                error="UTF-8 / CP932 のいずれでもデコードできませんでした",
            )

        suffix = p.suffix.lower()
        if suffix in _MARKDOWN_SUFFIXES:
            kind = LoaderKind.MARKDOWN
        elif suffix in _CODE_SUFFIXES:
            kind = LoaderKind.CODE
        else:
            kind = LoaderKind.PLAIN

        return LoaderResult(path=p, kind=kind, raw_text=text, size_bytes=size)
