"""hve.gui.doc_convert — 添付ファイルの Markdown 変換ユーティリティ。

設計書 §7.3 / §11.2 U6 対応。

サポート方針:
  - 既定で利用可能（純 stdlib のみ）: `.md` / `.markdown` / `.txt` / `.csv`
  - 任意依存（`markitdown[all]`）: `.html` / `.htm` / `.docx` / `.pdf` / `.xlsx`
    / `.pptx` / `.xls` — `pip install -e .[gui-docconvert]` で導入
    （通常は hve/setup-hve.ps1 --WithGui / hve/setup-hve.sh --with-gui で自動）
  - 未対応形式は `ConversionResult(ok=False, error=...)` を返す（呼び出し側でスキップ）

変換エンジン:
  - 任意依存対象は microsoft/markitdown (`MarkItDown.convert_local()`) に一本化。
  - 旧 pypdf / mammoth / markdownify / openpyxl 経路は撤去済み。

セキュリティ:
  - MarkItDown はローカルファイル限定の `convert_local()` のみを呼び出す
    （URL/ストリーム経路は使用しない）。
  - 入力ファイルサイズに上限を設けない（GUI 側でユーザーに警告を表示）
  - 変換結果はテキストのみ（バイナリは保存しない）
  - 出力ファイル名は ASCII 安全文字に正規化（設計書 §7.4）

注意:
  - 本モジュールは PySide6 に依存しない（純 Python）。GUI テストなしで単体テスト可能。
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# ASCII 安全文字以外を `_` に置換するパターン
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

# MarkItDown で変換する拡張子（任意依存）
_MARKITDOWN_EXTS = frozenset({
    ".html", ".htm",
    ".docx", ".pdf",
    ".xlsx", ".xls",
    ".pptx",
})


@dataclass
class ConversionResult:
    """1 ファイルの変換結果。"""

    src_path: Path
    """元のファイルパス（ユーザーが D&D した場所）。"""

    converted_path: Optional[Path] = None
    """変換後の Markdown ファイルパス（成功時のみ）。"""

    ok: bool = False
    error: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.src_path.name


def supported_extensions() -> List[str]:
    """このモジュールで変換可能な拡張子一覧を返す（任意依存含む）。"""
    return [
        ".md", ".markdown", ".txt", ".csv",
        ".html", ".htm", ".docx", ".pdf",
        ".xlsx", ".xls", ".pptx",
    ]


def is_supported(path: Path) -> bool:
    """ファイルがサポート対象かを返す（任意依存は未インストールでも True）。"""
    return path.suffix.lower() in supported_extensions()


def safe_filename(name: str) -> str:
    """ASCII 安全な Markdown ファイル名に正規化する。

    例:
      "Business Plan (2026).pdf" -> "Business_Plan_2026_.md"
      "メモ.txt"                  -> "_.md"  → これはダメなので呼び出し側で
                                              `name1.md` 等にリネームする
    """
    stem = Path(name).stem
    safe = _UNSAFE_NAME_RE.sub("_", stem).strip("_")
    if not safe:
        safe = "file"
    return f"{safe}.md"


def convert_file(
    src: Path,
    *,
    out_dir: Path,
    out_name: Optional[str] = None,
) -> ConversionResult:
    """1 ファイルを Markdown に変換して `out_dir/<safe_name>.md` に書き出す。

    Args:
        src: 入力ファイルのパス（存在チェックは呼び出し側）
        out_dir: 出力ディレクトリ（存在しなければ作成）
        out_name: 出力ファイル名（省略時は `safe_filename(src.name)`）

    Returns:
        ConversionResult: 成功時 ok=True / converted_path 設定、失敗時 ok=False / error 設定
    """
    if not src.exists():
        return ConversionResult(src_path=src, ok=False, error=f"ファイルが存在しません: {src}")
    if not src.is_file():
        return ConversionResult(src_path=src, ok=False, error=f"ファイルではありません: {src}")

    out_dir.mkdir(parents=True, exist_ok=True)
    target_name = out_name or safe_filename(src.name)
    target = out_dir / target_name

    suffix = src.suffix.lower()
    try:
        if suffix in (".md", ".markdown"):
            content = _read_text(src)
        elif suffix == ".txt":
            content = _convert_txt(src)
        elif suffix == ".csv":
            content = _convert_csv(src)
        elif suffix in _MARKITDOWN_EXTS:
            content = _convert_with_markitdown(src)
        else:
            return ConversionResult(
                src_path=src,
                ok=False,
                error=f"未対応の拡張子です: {suffix}",
            )
    except _OptionalDependencyMissing as e:
        return ConversionResult(src_path=src, ok=False, error=str(e))
    except Exception as e:
        return ConversionResult(
            src_path=src,
            ok=False,
            error=f"変換失敗 ({suffix}): {type(e).__name__}: {e}",
        )

    try:
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        return ConversionResult(
            src_path=src,
            ok=False,
            error=f"書き込み失敗: {e}",
        )

    return ConversionResult(src_path=src, converted_path=target, ok=True)


# --------------------------------------------------------------------------
# 内部変換関数（純 stdlib）
# --------------------------------------------------------------------------


def _read_text(src: Path) -> str:
    """テキストファイルを UTF-8 で読み込み、BOM があれば除去する。"""
    raw = src.read_bytes()
    # BOM 除去
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    # フォールバック: UTF-8 → CP932 → Latin-1
    for enc in ("utf-8", "cp932", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _convert_txt(src: Path) -> str:
    """テキストファイルを Markdown ヘッダ付きで返す。"""
    text = _read_text(src)
    return f"# {src.stem}\n\n```\n{text}\n```\n"


def _convert_csv(src: Path) -> str:
    """CSV を Markdown 表に変換する（行数制限なし）。"""
    text = _read_text(src)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return f"# {src.stem}\n\n（空の CSV ファイル）\n"

    header, *body = rows
    out = [f"# {src.stem}", ""]
    out.append("| " + " | ".join(_md_escape_cell(c) for c in header) + " |")
    out.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in body:
        # 列数不足は空セルで補う / 余剰はそのまま結合
        cells = list(row) + [""] * (len(header) - len(row))
        out.append("| " + " | ".join(_md_escape_cell(c) for c in cells[: len(header)]) + " |")
    out.append("")
    return "\n".join(out)


def _md_escape_cell(s: str) -> str:
    """Markdown 表セル内の `|` と改行をエスケープする。"""
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", "")


# --------------------------------------------------------------------------
# 任意依存（pip install -e .[gui-docconvert] が必要、markitdown を使用）
# --------------------------------------------------------------------------


class _OptionalDependencyMissing(Exception):
    """任意依存ライブラリ（markitdown）が未インストールであることを示す例外。"""


def _convert_with_markitdown(src: Path) -> str:
    """MarkItDown で各種ドキュメントを Markdown に変換する。

    対象: `.html` / `.htm` / `.docx` / `.pdf` / `.xlsx` / `.xls` / `.pptx`
    依存: `pip install -e .[gui-docconvert]`（中身は `markitdown[all]`）

    セキュリティ: ローカルファイル限定の `convert_local()` のみを呼び出す。
    """
    try:
        from markitdown import MarkItDown  # type: ignore[import-not-found]
    except ImportError as e:
        raise _OptionalDependencyMissing(
            "ドキュメント変換には markitdown が必要です。\n"
            "  hve/setup-hve.ps1 --WithGui  または  hve/setup-hve.sh --with-gui\n"
            "  あるいは手動で:  pip install -e .[gui,gui-docconvert]"
        ) from e

    md = MarkItDown(enable_plugins=False)
    result = md.convert_local(str(src))
    text = getattr(result, "text_content", None) or getattr(result, "markdown", "") or ""
    return str(text)
