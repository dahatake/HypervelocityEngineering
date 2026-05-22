"""tools/wrap_tr.py — GUI ソース内の日本語文字列を ``self.tr(...)`` でラップする補助ツール。

設計:
  - Python の ``ast`` モジュールでソースを解析し、対象となる文字列リテラルノードの
    (lineno, col_offset, end_lineno, end_col_offset) を収集する。
  - 取得した位置情報を後方から処理し、ソース上のバイト範囲を ``self.tr(<元文字列>)`` に
    置換する（後方処理によりオフセットが変動しても安全）。
  - ``ast.unparse`` は使わない（フォーマットが崩れる）。元のソースをバイト単位で編集。

対象パターン（Call ノードの第 1 引数 / 指定キーワード引数の文字列リテラルが対象）:

  1. クラス呼び出しの第 1 引数:
       ``QLabel("...")`` / ``QPushButton("...")`` / ``QCheckBox("...")`` /
       ``QRadioButton("...")`` / ``QToolButton("...")`` / ``QGroupBox("...")``
  2. メソッド呼び出しの第 1 引数（属性名でフィルタ）:
       ``.setText("...")`` / ``.setPlaceholderText("...")`` / ``.setToolTip("...")`` /
       ``.setStatusTip("...")`` / ``.setWhatsThis("...")`` / ``.setTitle("...")`` /
       ``.setWindowTitle("...")``
  3. ``ComboBox.addItem(...)`` / ``.addAction(...)`` / ``.addTab(...)`` の第 1 引数
  4. キーワード引数: ``title=``, ``description=``, ``filters=``, ``tooltip=``,
     ``text=``, ``placeholder=`` の文字列リテラル値
  5. ``QMessageBox.warning/information/question/critical/about`` の第 2・第 3 引数

ラップ条件:
  - 文字列リテラル（``ast.Constant`` で ``isinstance(value, str)``）であること
  - 暗黙連結も含めて少なくとも 1 文字以上の **日本語文字** を含むこと
    （日本語: U+3040-U+309F, U+30A0-U+30FF, U+4E00-U+9FFF, 全角記号 U+FF00-U+FFEF）
  - 既に ``self.tr(...)`` / ``self.tr_lazy(...)`` / ``QCoreApplication.translate(...)`` /
    ``QT_TRANSLATE_NOOP(...)`` の引数になっていないこと（親 Call の name でチェック）
  - 親関数（``FunctionDef``/``AsyncFunctionDef``）内で第 1 引数名が ``self`` または ``cls`` であること
    （= ``self.tr`` が呼び出せるスコープ）。それ以外（モジュールトップ・staticmethod 等）は
    スキップしてレポートにのみ出力する。

使用法:
  ``python tools/wrap_tr.py [--check] [--report PATH] <file1.py> [<file2.py> ...]``

  - ``--check``: 書き換えを行わず、対象箇所のレポートのみ出力（dry-run）
  - ``--report PATH``: 対象/スキップ箇所を Markdown レポートとして出力

注意:
  本ツールは新規 ``self.tr(...)`` 呼び出し追加のみを行う。既存の翻訳マーカーや
  ``QT_TRANSLATE_NOOP`` には触れない。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# 対象パターン定義
# ---------------------------------------------------------------------------
_TARGET_CLASS_NAMES: Set[str] = {
    "QLabel",
    "QPushButton",
    "QCheckBox",
    "QRadioButton",
    "QToolButton",
    "QGroupBox",
    "QAction",
}

_TARGET_METHOD_NAMES: Set[str] = {
    "setText",
    "setPlaceholderText",
    "setToolTip",
    "setStatusTip",
    "setWhatsThis",
    "setTitle",
    "setWindowTitle",
    "addItem",
    "addAction",
    "addTab",
    "setItemText",
    "setTabText",
}

_TARGET_KWARG_NAMES: Set[str] = {
    "title",
    "description",
    "filters",
    "tooltip",
    "text",
    "placeholder",
    "label",
}

# 既に翻訳済み / 翻訳マーカーの呼び出し名（これらの引数はスキップ）
_TRANSLATION_WRAPPER_NAMES: Set[str] = {
    "tr",
    "translate",
    "tr_lazy",
    "QT_TRANSLATE_NOOP",
    "QT_TR_NOOP",
    "QT_TR_NOOP_UTF8",
    "QT_TRANSLATE_NOOP_UTF8",
    "QT_TRANSLATE_NOOP3",
    "trUtf8",
    "_tr",
    "_",  # gettext 慣用
}

# QMessageBox の静的メソッド名（第 2・第 3 引数）
_MESSAGEBOX_STATIC_METHODS: Set[str] = {
    "warning",
    "information",
    "question",
    "critical",
    "about",
}

# 日本語と判定する Unicode 範囲
_JP_RE = re.compile(
    r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF]"
)


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------
@dataclass
class WrapTarget:
    """ラップ対象の文字列リテラル 1 件。"""

    lineno: int  # 1-based
    col_offset: int  # 0-based, byte offset within line (ast は UTF-8 バイト基準)
    end_lineno: int
    end_col_offset: int
    text_preview: str  # 先頭 40 文字
    pattern: str  # どのパターンで採用したか（ログ用）


@dataclass
class FileReport:
    path: Path
    wrapped: List[WrapTarget] = field(default_factory=list)
    skipped_no_self: List[WrapTarget] = field(default_factory=list)
    already_wrapped: int = 0


# ---------------------------------------------------------------------------
# AST 解析
# ---------------------------------------------------------------------------
def _has_jp(text: str) -> bool:
    return bool(_JP_RE.search(text))


def _get_call_name(call: ast.Call) -> Optional[str]:
    """Call.func から呼び出し名を抽出する。

    ``QLabel(...)`` -> ``"QLabel"``
    ``self.tr(...)`` -> ``"tr"``
    ``QMessageBox.warning(...)`` -> ``"warning"``
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _get_messagebox_static_name(call: ast.Call) -> Optional[str]:
    """``QMessageBox.warning(...)`` のような形なら ``"warning"`` を返す。"""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "QMessageBox" and func.attr in _MESSAGEBOX_STATIC_METHODS:
            return func.attr
    return None


def _is_string_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _string_value(node: ast.expr) -> str:
    assert isinstance(node, ast.Constant) and isinstance(node.value, str)
    return node.value


class _Collector(ast.NodeVisitor):
    """AST を走査して WrapTarget を収集する。"""

    def __init__(self) -> None:
        self.targets: List[WrapTarget] = []
        self.skipped_no_self: List[WrapTarget] = []
        self.already_wrapped = 0
        # スタック: 現在のスコープが ``self`` を持つメソッド内かどうか
        self._self_scope_stack: List[bool] = [False]
        # スタック: 現在の Call ノード（親が翻訳ラッパーか判定する用）
        self._call_parent_names: List[str] = []

    # ---- スコープ管理 ----
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._enter_func(node)
        self.generic_visit(node)
        self._self_scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._enter_func(node)
        self.generic_visit(node)
        self._self_scope_stack.pop()

    def _enter_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        first_arg = node.args.args[0].arg if node.args.args else ""
        has_self = first_arg in ("self", "cls")
        self._self_scope_stack.append(has_self)

    def _in_self_scope(self) -> bool:
        return self._self_scope_stack[-1]

    # ---- Call 解析 ----
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        call_name = _get_call_name(node) or ""
        mb_static = _get_messagebox_static_name(node)

        # 既に翻訳ラッパー内なら、その引数は対象外（ただし子要素は走査続行）
        if call_name in _TRANSLATION_WRAPPER_NAMES:
            self._call_parent_names.append(call_name)
            for arg in node.args:
                if _is_string_literal(arg) and _has_jp(_string_value(arg)):
                    self.already_wrapped += 1
            self.generic_visit(node)
            self._call_parent_names.pop()
            return

        # ① クラスコンストラクタ系: 第 1 引数のみ対象
        if call_name in _TARGET_CLASS_NAMES and node.args:
            self._try_add_positional(node.args[0], pattern=f"{call_name}(arg0)")

        # ② メソッド呼び出し系: 第 1 引数のみ対象
        if call_name in _TARGET_METHOD_NAMES and node.args:
            self._try_add_positional(node.args[0], pattern=f".{call_name}(arg0)")

        # ③ QMessageBox.<static>(self, title, text, ...): 第 2・第 3 引数
        if mb_static is not None:
            for idx in (1, 2):
                if idx < len(node.args):
                    self._try_add_positional(node.args[idx], pattern=f"QMessageBox.{mb_static}(arg{idx})")

        # ④ キーワード引数
        for kw in node.keywords:
            if kw.arg in _TARGET_KWARG_NAMES and _is_string_literal(kw.value):
                self._try_add(kw.value, pattern=f"{call_name or '?'}({kw.arg}=)")

        self.generic_visit(node)

    # ---- 対象登録 ----
    def _try_add_positional(self, node: ast.expr, *, pattern: str) -> None:
        if _is_string_literal(node):
            self._try_add(node, pattern=pattern)

    def _try_add(self, node: ast.expr, *, pattern: str) -> None:
        assert isinstance(node, ast.Constant) and isinstance(node.value, str)
        text = node.value
        if not _has_jp(text):
            return
        if node.end_lineno is None or node.end_col_offset is None:
            return
        target = WrapTarget(
            lineno=node.lineno,
            col_offset=node.col_offset,
            end_lineno=node.end_lineno,
            end_col_offset=node.end_col_offset,
            text_preview=text[:40].replace("\n", "\\n"),
            pattern=pattern,
        )
        if self._in_self_scope():
            self.targets.append(target)
        else:
            self.skipped_no_self.append(target)


# ---------------------------------------------------------------------------
# ソース書き換え
# ---------------------------------------------------------------------------
def _wrap_source(source: str, targets: List[WrapTarget]) -> str:
    """``targets`` の位置を後方から ``self.tr(<orig>)`` で囲む。

    ast の col_offset は **UTF-8 バイト** ベースのため、行をバイト列として扱う。
    """
    if not targets:
        return source

    lines = source.splitlines(keepends=True)
    # バイト列に変換
    line_bytes = [ln.encode("utf-8") for ln in lines]

    # 重複/重なりを排除し、後方から処理
    sorted_targets = sorted(
        targets,
        key=lambda t: (t.end_lineno, t.end_col_offset),
        reverse=True,
    )

    # 重なる対象を除外（先に処理する後方優先）
    seen_ranges: List[Tuple[int, int, int, int]] = []  # (sl, sc, el, ec)

    def _overlaps(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
        # 区間 [(sl, sc), (el, ec)) の重なり判定
        a_start = (a[0], a[1])
        a_end = (a[2], a[3])
        b_start = (b[0], b[1])
        b_end = (b[2], b[3])
        return not (a_end <= b_start or b_end <= a_start)

    for t in sorted_targets:
        rng = (t.lineno, t.col_offset, t.end_lineno, t.end_col_offset)
        if any(_overlaps(rng, s) for s in seen_ranges):
            continue
        seen_ranges.append(rng)

        # 元バイト列を抽出
        sl, sc, el, ec = rng
        if sl == el:
            orig_bytes = line_bytes[sl - 1][sc:ec]
            new_bytes = b"self.tr(" + orig_bytes + b")"
            line_bytes[sl - 1] = (
                line_bytes[sl - 1][:sc] + new_bytes + line_bytes[sl - 1][ec:]
            )
        else:
            # 複数行（暗黙連結）の場合
            first = line_bytes[sl - 1][sc:]
            middle = b"".join(line_bytes[sl : el - 1])
            last = line_bytes[el - 1][:ec]
            orig_bytes = first + middle + last
            new_bytes = b"self.tr(" + orig_bytes + b")"
            # sl-1 行から el-1 行までを 1 行に集約せず、元の行構成を保つために
            # 最初の行の sc 以降と最後の行の :ec を新バイトに置換する形をとる。
            # 安全のため、複数行の場合は全行を 1 行ぶんへ統合する方針:
            #   - 行 sl-1: [...:sc] + new_bytes
            #   - 行 sl..el-1: 削除（行末改行のみ最後尾に保持）
            #   - 行 el-1: [ec:]
            line_bytes[sl - 1] = line_bytes[sl - 1][:sc] + new_bytes
            tail = line_bytes[el - 1][ec:]
            # 中間行と el-1 行は削除
            del line_bytes[sl : el]
            # tail を結合
            line_bytes[sl - 1] = line_bytes[sl - 1] + tail

    return b"".join(line_bytes).decode("utf-8")


# ---------------------------------------------------------------------------
# ファイル処理
# ---------------------------------------------------------------------------
def process_file(path: Path, *, write: bool) -> FileReport:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    collector = _Collector()
    collector.visit(tree)

    report = FileReport(path=path)
    report.wrapped = list(collector.targets)
    report.skipped_no_self = list(collector.skipped_no_self)
    report.already_wrapped = collector.already_wrapped

    if write and collector.targets:
        new_source = _wrap_source(source, collector.targets)
        path.write_text(new_source, encoding="utf-8")

    return report


def _format_report_md(reports: Iterable[FileReport]) -> str:
    lines: List[str] = ["# wrap_tr.py レポート", ""]
    for r in reports:
        lines.append(f"## {r.path}")
        lines.append("")
        lines.append(f"- ラップ対象: **{len(r.wrapped)}** 件")
        lines.append(f"- self/cls スコープ外でスキップ: {len(r.skipped_no_self)} 件")
        lines.append(f"- 既にラップ済み: {r.already_wrapped} 件")
        lines.append("")
        if r.wrapped:
            lines.append("### ラップ対象")
            lines.append("")
            lines.append("| 行 | パターン | プレビュー |")
            lines.append("|---|---|---|")
            for t in r.wrapped:
                lines.append(f"| {t.lineno} | {t.pattern} | `{t.text_preview}` |")
            lines.append("")
        if r.skipped_no_self:
            lines.append("### スキップ（self/cls 外）")
            lines.append("")
            lines.append("| 行 | パターン | プレビュー |")
            lines.append("|---|---|---|")
            for t in r.skipped_no_self:
                lines.append(f"| {t.lineno} | {t.pattern} | `{t.text_preview}` |")
            lines.append("")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Wrap Japanese string literals with self.tr() in Python source files.")
    parser.add_argument("files", nargs="+", type=Path, help="Target .py files")
    parser.add_argument("--check", action="store_true", help="Do not write; only report")
    parser.add_argument("--report", type=Path, default=None, help="Write Markdown report to this path")
    args = parser.parse_args(argv)

    reports: List[FileReport] = []
    for p in args.files:
        if not p.is_file():
            print(f"skip (not a file): {p}", file=sys.stderr)
            continue
        rep = process_file(p, write=not args.check)
        reports.append(rep)
        action = "would-wrap" if args.check else "wrapped"
        print(
            f"[{action}] {p}: {len(rep.wrapped)} target(s), "
            f"{len(rep.skipped_no_self)} skipped, {rep.already_wrapped} already"
        )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_format_report_md(reports), encoding="utf-8")
        print(f"report written to {args.report}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
