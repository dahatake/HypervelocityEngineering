"""doc_ingest.py — ADI ワークフローの決定的前処理。

``docs-original/`` 配下の原本を走査し、Markdown へ正規化して
``docs/original-design-doc-ingest/`` に派生物と目録（``index.json``）を出力する。

設計方針:
- **決定的**: 同一入力に対し ``index.json`` の ``docs`` / ``excluded`` は常に同一（FR-WF-ADI-01）
- **原本不変**: ``source_dir`` へは一切書き込まない（FR-WF-ADI-02）
- **fail-closed**: 文書数が上限を超えたら例外を投げ、目録を書かない（FR-WF-ADI-10）
- **差分スキップ**: ``sha256`` が前回と一致する文書は派生物を再書き込みしない（FR-WF-ADI-11）
- **パストラバーサル防止**: ``source_dir`` 外を指すシンボリックリンクは走査しない（NFR-SEC-ADI-02）

変換は ``hve.gui.doc_convert.convert_file``（microsoft/markitdown ベース）へ委譲する。
同モジュールは PySide6 に依存しないため CLI からも利用できる。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .gui.doc_convert import convert_file, is_supported

# 目録ファイル名
INDEX_FILENAME = "index.json"
# 1 実行あたりの文書数上限（安全弁。超過時は fail-closed）
MAX_DOCS = 200
# 派生物のファイル名
CONTENT_FILENAME = "content.md"
PROVENANCE_FILENAME = "provenance.json"

_NON_ASCII_RE = re.compile(r"[^A-Za-z0-9]+")
# doc_convert 側の変換経路と対応させる（provenance の正確性のため）
_PASSTHROUGH_EXTS = frozenset({".md", ".markdown"})
_STDLIB_EXTS = frozenset({".txt", ".csv"})


class MaxDocsExceededError(Exception):
    """走査対象の文書数が上限を超えた場合に投げる。"""


@dataclass
class IngestedDoc:
    doc_id: str
    slug: str
    source_path: str
    sha256: str
    bytes: int
    ext: str
    converter: str
    content_path: str
    duplicate_of: Optional[str] = None


@dataclass
class ExcludedDoc:
    source_path: str
    reason: str


def _converter_name(ext: str) -> str:
    """拡張子から実際に使われる変換経路名を返す。"""
    if ext in _PASSTHROUGH_EXTS:
        return "passthrough"
    if ext in _STDLIB_EXTS:
        return "stdlib"
    return "markitdown"


def _slug(index: int, name: str) -> str:
    """``doc-0001-agelas10201`` 形式の ASCII 安全なディレクトリ名を返す。"""
    ascii_part = _NON_ASCII_RE.sub("-", Path(name).stem).strip("-").lower()
    base = f"doc-{index:04d}"
    return f"{base}-{ascii_part}" if ascii_part else base


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _is_inside(path: Path, base: Path) -> bool:
    """``path`` の実体が ``base`` 配下かを返す（シンボリックリンク解決後で判定）。"""
    try:
        path.resolve(strict=True).relative_to(base.resolve(strict=True))
    except (ValueError, OSError):
        return False
    return True


def _collect_files(source_dir: Path) -> List[Path]:
    """``source_dir`` 配下のファイルを相対パス昇順で返す。"""
    return sorted(
        (p for p in source_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(source_dir).as_posix(),
    )


def _read_previous_sha(doc_dir: Path) -> Optional[str]:
    prov = doc_dir / PROVENANCE_FILENAME
    if not prov.is_file() or not (doc_dir / CONTENT_FILENAME).is_file():
        return None
    try:
        return json.loads(prov.read_text(encoding="utf-8")).get("sha256")
    except (OSError, ValueError):
        return None


def ingest_docs(
    source_dir: Path,
    *,
    out_dir: Path,
    max_docs: int = MAX_DOCS,
) -> Dict[str, object]:
    """``source_dir`` を走査して ``out_dir`` に派生物と ``index.json`` を出力する。

    Args:
        source_dir: 原本ディレクトリ（読み取り専用として扱う）
        out_dir: 派生物の出力先
        max_docs: 走査対象ファイル数の上限

    Returns:
        ``index.json`` に書いた辞書。

    Raises:
        MaxDocsExceededError: 走査対象が ``max_docs`` を超えた場合（何も書き込まない）
    """
    source_dir = Path(source_dir)
    out_dir = Path(out_dir)

    files = _collect_files(source_dir)
    if len(files) > max_docs:
        raise MaxDocsExceededError(
            f"{source_dir} 配下のファイル数 {len(files)} が上限 {max_docs} を超えています。"
            "対象を分割して実行してください。"
        )

    docs: List[IngestedDoc] = []
    excluded: List[ExcludedDoc] = []
    sha_to_doc_id: Dict[str, str] = {}
    seq = 0

    for path in files:
        rel = path.relative_to(source_dir).as_posix()

        if not _is_inside(path, source_dir):
            excluded.append(ExcludedDoc(rel, "source_dir 外を指すシンボリックリンク"))
            continue

        ext = path.suffix.lower()
        if not is_supported(path):
            excluded.append(ExcludedDoc(rel, f"未対応の拡張子です: {ext}"))
            continue

        # 採番後の変換失敗は欠番として扱う（番号を戻すと前回実行の残骸 dir と衝突する）。
        seq += 1
        slug = _slug(seq, path.name)
        doc_dir = out_dir / slug
        digest = _sha256(path)
        doc_id = f"DOC-{seq:04d}"
        converter = _converter_name(ext)

        if _read_previous_sha(doc_dir) != digest:
            result = convert_file(path, out_dir=doc_dir, out_name=CONTENT_FILENAME)
            if not result.ok:
                excluded.append(ExcludedDoc(rel, result.error or "変換に失敗しました"))
                _remove_if_empty(doc_dir)
                continue
            (doc_dir / PROVENANCE_FILENAME).write_text(
                json.dumps(
                    {"source_path": rel, "sha256": digest, "converter": converter},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        docs.append(
            IngestedDoc(
                doc_id=doc_id,
                slug=slug,
                source_path=rel,
                sha256=digest,
                bytes=path.stat().st_size,
                ext=ext,
                converter=converter,
                # out_dir を丸ごと含める（`.name` だけだと入れ子の out_dir で親が落ちる）。
                content_path=f"{out_dir.as_posix()}/{slug}/{CONTENT_FILENAME}",
                duplicate_of=sha_to_doc_id.get(digest),
            )
        )
        sha_to_doc_id.setdefault(digest, doc_id)

    return _write_index(out_dir, docs, excluded)


def _remove_if_empty(doc_dir: Path) -> None:
    """変換失敗で生じた空ディレクトリを削除する。"""
    try:
        doc_dir.rmdir()
    except OSError:
        pass


def _write_index(
    out_dir: Path,
    docs: List[IngestedDoc],
    excluded: List[ExcludedDoc],
) -> Dict[str, object]:
    """``index.json`` を書き出す。内容が前回と同一なら ``generated_at`` を据え置く。"""
    payload: Dict[str, object] = {
        "converter": "markitdown",
        "docs": [asdict(d) for d in docs],
        "excluded": [asdict(e) for e in excluded],
    }

    index_path = out_dir / INDEX_FILENAME
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if index_path.is_file():
        try:
            previous = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        if previous.get("docs") == payload["docs"] and previous.get("excluded") == payload["excluded"]:
            generated_at = previous.get("generated_at", generated_at)

    payload = {"generated_at": generated_at, **payload}
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload
