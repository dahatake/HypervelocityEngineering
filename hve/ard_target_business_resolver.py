"""ard_target_business_resolver.py — ARD Step 2 の target_business パス展開モジュール。

ARD ワークフローの Step 2（Targeted 事業分析）で、`target_business` パラメータが
文章ではなく **フォルダパスまたは複数ファイルパス** で指定された場合に、
それらをファイル群として読み込んで Step 2 のプロンプト context として整形する。

PR#5 のスコープ:
- is_path_like: 文章 vs パスの簡易ヒューリスティック判定
- resolve: パス指定の値をファイル群に展開（サイズ上限・件数上限・バイナリスキップ）
- to_context_text: 整形して Step 2 用 context 文字列を生成

セキュリティ・運用上の制約:
- max_files=50 / max_total_bytes=5 MiB / max_file_bytes=1 MiB がデフォルト上限
- バイナリファイル（PDF/DOCX 等）は読み込まずスキップ理由を記録
- base_dir 外のシンボリックリンクはスキップ（パストラバーサル防止）
- 例外を投げず errors / skipped に記録して継続
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, List, Optional


_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".zip", ".tar", ".gz", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".ico",
    ".mp3", ".mp4", ".mov", ".avi",
    ".exe", ".bin", ".so", ".dll",
})

_DEFAULT_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".csv", ".json", ".yaml", ".yml",
    ".html", ".htm", ".rst",
})

_PATH_LIKE_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".pdf", ".docx", ".xlsx", ".csv",
    ".json", ".yaml", ".yml", ".html", ".htm", ".rst",
})

_JAPANESE_SENTENCE_RE = re.compile(r"[。、]")


@dataclass
class ResolvedFile:
    """展開された 1 ファイルの情報。"""

    path: Path
    relative_path: str
    size_bytes: int
    truncated: bool
    content: str
    skip_reason: Optional[str] = None


@dataclass
class ResolvedTargetBusiness:
    """target_business のパス展開結果。"""

    is_path: bool
    raw_text: str
    files: List[ResolvedFile] = field(default_factory=list)
    folders: List[Path] = field(default_factory=list)
    total_size_bytes: int = 0
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def is_path_like(value: str, *, base_dir: Optional[Path] = None) -> bool:
    """target_business の文字列値がパス指定か文章かを簡易判定する。

    迷う場合は文章扱い（False）を優先する保守的な判定。
    base_dir を指定すると相対パスの存在確認にそのディレクトリを使用する。
    """
    stripped = value.strip()

    if not stripped:
        return False

    if "\n" in value:
        return False

    if len(stripped) > 200:
        return False

    if _JAPANESE_SENTENCE_RE.search(stripped):
        return False

    tokens = [t for t in re.split(r"[,\s]+", stripped) if t]
    if not tokens:
        return False

    for token in tokens:
        if "/" in token or "\\" in token:
            continue
        token_path = Path(token)
        check_path = (
            base_dir / token_path
            if base_dir is not None and not token_path.is_absolute()
            else token_path
        )
        if check_path.exists():
            continue
        if token_path.suffix.lower() in _PATH_LIKE_EXTENSIONS:
            continue
        return False

    return True


def _split_paths(value: str) -> List[str]:
    """カンマおよび空白で区切ってパストークンのリストを返す。

    カンマと空白が混在する場合も正しく分割する（例: "a.md, b.md c.md" → 3 件）。
    """
    return [t for t in re.split(r"[,\s]+", value.strip()) if t]


def _resolve_path(token: str, base_dir: Optional[Path]) -> Path:
    p = Path(token)
    if not p.is_absolute() and base_dir is not None:
        return base_dir / p
    return p


def _relative_str(path: Path, base_dir: Optional[Path]) -> str:
    if base_dir is not None:
        try:
            return str(path.relative_to(base_dir))
        except ValueError:
            pass
    return str(path)


def _is_safe_path(path: Path, base_dir: Optional[Path]) -> bool:
    """パスが base_dir 内に解決されることを確認する。

    シンボリックリンクや `..` を含むパス、親ディレクトリがシンボリックリンクの
    ケースも含めて、常に resolve() 後のパスで base_dir との包含関係を検証する。
    base_dir が None の場合は常に True を返す。
    """
    if base_dir is None:
        return True
    try:
        resolved = path.resolve()
        base_resolved = base_dir.resolve()
        resolved.relative_to(base_resolved)
        return True
    except (ValueError, OSError):
        return False


def _iter_candidates(
    tokens: List[str],
    base_dir: Optional[Path],
    result: ResolvedTargetBusiness,
) -> Generator[Path, None, None]:
    """トークンリストからファイル候補を遅延評価で yield する。

    ディレクトリは rglob で再帰展開する。sorted による事前全件収集は行わず、
    呼び出し側が件数/サイズ上限に達した時点で消費を止めることができる。
    """
    for token in tokens:
        path = _resolve_path(token, base_dir)
        try:
            if not path.exists():
                result.errors.append(f"パスが存在しません: {token}")
                continue

            if path.is_dir():
                result.folders.append(path)
                try:
                    for file_path in path.rglob("*"):
                        if file_path.is_file():
                            yield file_path
                except OSError as e:
                    result.errors.append(f"ディレクトリ列挙エラー ({token}): {e}")
            elif path.is_file():
                yield path
            else:
                result.errors.append(f"パスが不明な種類: {token}")

        except OSError as e:
            result.errors.append(f"パスアクセスエラー ({token}): {e}")


def resolve(
    value: str,
    *,
    base_dir: Optional[Path] = None,
    max_files: int = 50,
    max_total_bytes: int = 5 * 1024 * 1024,
    max_file_bytes: int = 1 * 1024 * 1024,
    allowed_extensions: Optional[set[str]] = None,
) -> ResolvedTargetBusiness:
    """target_business 値を解析してファイル群に展開する。

    - value がパス指定でないと判定された場合、is_path=False で raw_text のみ設定して返す。
    - パス指定の場合:
      - カンマまたは空白区切りで複数パスを受け付ける
      - フォルダの場合は **再帰的** にテキストファイルを列挙
      - allowed_extensions を指定した場合はその拡張子のみ収集（デフォルト: .md/.txt/.csv/.json/.yaml/.yml/.html/.htm/.rst）
      - PDF/DOCX/XLSX 等のバイナリは skip_reason を設定して content は空文字
      - max_files / max_total_bytes / max_file_bytes を超える場合は途中で打ち切り、skipped に理由を追加
      - base_dir 外に解決されるパス（シンボリックリンク・`..` 含む）は skipped 扱い（パストラバーサル防止）
    - 例外を投げない（致命的なものも errors にメッセージで記録して continue）
    """
    result = ResolvedTargetBusiness(
        is_path=is_path_like(value, base_dir=base_dir),
        raw_text=value,
    )

    if not result.is_path:
        return result

    effective_extensions: frozenset[str] = (
        frozenset(ext.lower() for ext in allowed_extensions)
        if allowed_extensions is not None
        else _DEFAULT_ALLOWED_EXTENSIONS
    )

    tokens = _split_paths(value)
    readable_count = 0

    for file_path in _iter_candidates(tokens, base_dir, result):
        relative = _relative_str(file_path, base_dir)

        # base_dir 外に解決されるパス（symlink・.. 含む）はスキップ
        if not _is_safe_path(file_path, base_dir):
            result.skipped.append(f"{relative}: base_dir 外を指すパスのためスキップ")
            continue

        suffix = file_path.suffix.lower()

        # バイナリ拡張子チェック
        if suffix in _BINARY_EXTENSIONS:
            try:
                file_size = file_path.stat().st_size
            except OSError:
                file_size = 0
            rf = ResolvedFile(
                path=file_path,
                relative_path=relative,
                size_bytes=file_size,
                truncated=False,
                content="",
                skip_reason=f"バイナリファイル（{suffix}）はスキップ",
            )
            result.files.append(rf)
            result.skipped.append(f"{relative}: {rf.skip_reason}")
            continue

        # 拡張子フィルタ（バイナリ以外）
        if suffix not in effective_extensions:
            result.skipped.append(f"{relative}: 対象外の拡張子（{suffix}）のためスキップ")
            continue

        # 件数上限チェック（読み込み可能ファイルのみカウント）
        if readable_count >= max_files:
            result.skipped.append(f"{relative}: max_files={max_files} 上限に達したためスキップ")
            continue

        # ファイルサイズ取得
        try:
            file_size = file_path.stat().st_size
        except OSError as e:
            result.errors.append(f"{relative}: stat 失敗: {e}")
            continue

        # 累積サイズ上限の事前チェック（raw bytes ベースで統一）
        bytes_to_read = min(file_size, max_file_bytes)
        if result.total_size_bytes + bytes_to_read > max_total_bytes:
            result.skipped.append(
                f"{relative}: max_total_bytes={max_total_bytes} 上限に達したためスキップ"
            )
            continue

        # ストリーミング読み込み（max_file_bytes を超えるファイルは全量読み込まない）
        try:
            with file_path.open("rb") as fh:
                raw = fh.read(max_file_bytes + 1)
        except OSError as e:
            result.errors.append(f"{relative}: 読み込みエラー: {e}")
            continue

        truncated = len(raw) > max_file_bytes
        if truncated:
            raw = raw[:max_file_bytes]

        # デコード（UnicodeDecodeError は切り詰め有無に関わらず常にスキップ）
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            rf = ResolvedFile(
                path=file_path,
                relative_path=relative,
                size_bytes=file_size,
                truncated=False,
                content="",
                skip_reason="UnicodeDecodeError: バイナリとして扱いスキップ",
            )
            result.files.append(rf)
            result.skipped.append(f"{relative}: {rf.skip_reason}")
            continue

        if truncated:
            content += f"\n... (truncated, original size: {file_size} bytes)"

        rf = ResolvedFile(
            path=file_path,
            relative_path=relative,
            size_bytes=file_size,
            truncated=truncated,
            content=content,
        )
        result.files.append(rf)
        result.total_size_bytes += len(raw)  # raw bytes で事前チェックと単位を統一
        readable_count += 1

    return result


def to_context_text(resolved: ResolvedTargetBusiness) -> str:
    """ResolvedTargetBusiness を Step 2 へ渡す context 文字列に整形する。

    形式（パス指定時）:
      ## target_business: ファイル展開結果

      指定パス: <元の値>
      展開ファイル数: <N>
      合計サイズ: <bytes>

      ### <相対パス1>
      ```
      <内容（max_file_bytes で切り詰め）>
      ```

      ### <相対パス2>
      ...

      （スキップしたファイル: <理由付き一覧>）

    パス指定でない場合は raw_text をそのまま返す。
    """
    if not resolved.is_path:
        return resolved.raw_text

    readable_files = [f for f in resolved.files if f.skip_reason is None]

    parts: List[str] = [
        "## target_business: ファイル展開結果",
        "",
        f"指定パス: {resolved.raw_text}",
        f"展開ファイル数: {len(readable_files)}",
        f"合計サイズ: {resolved.total_size_bytes}",
        "",
    ]

    for rf in readable_files:
        parts.append(f"### {rf.relative_path}")
        parts.append("```")
        parts.append(rf.content)
        parts.append("```")
        parts.append("")

    if resolved.skipped:
        parts.append("（スキップしたファイル:")
        for reason in resolved.skipped:
            parts.append(f"  - {reason}")
        parts.append("）")

    return "\n".join(parts)
