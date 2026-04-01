"""qa_merger.py — QA 質問票マージエンジン

QA 質問票ファイル（`qa/` 配下）を解析し、ユーザー回答をマージして
6列テーブル形式で保存する。統合ドキュメントのパス生成もサポートする。

ファイル構造:
    # タイトル

    **状態**: 回答待ち
    **推論許可**: なし
    ...

    ---

    [プレアンブル（任意）]

    ## 質問項目

    | No. | [追加列...] | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 | [ユーザー回答] |
    |-----|------------|------|--------|-------------------|----------|
    | 1 | ...
"""

from __future__ import annotations

import copy
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class Choice:
    """選択肢（例: A, B, C）"""
    label: str   # "A", "B", "C", ...
    text: str    # "別サービス維持（現行）"


@dataclass
class QAQuestion:
    """質問1件"""
    no: int
    question: str
    choices: List[Choice] = field(default_factory=list)
    default_answer: str = ""
    reason: str = ""
    user_answer: Optional[str] = None


@dataclass
class QADocument:
    """質問票ドキュメント全体"""
    title: str = ""
    status: str = "回答待ち"
    inference_permission: str = "なし"
    header_fields: List[Tuple[str, str]] = field(default_factory=list)
    preamble: str = ""
    questions: List[QAQuestion] = field(default_factory=list)
    raw_sections: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# QAMerger クラス
# ---------------------------------------------------------------------------

class QAMerger:
    """QA 質問票のパース・マージ・レンダリングを行うクラス。"""

    # ------------------------------------------------------------------
    # パース
    # ------------------------------------------------------------------

    @staticmethod
    def parse_qa_file(path: Path) -> QADocument:
        """qa/ ファイルを読み込んでパースする。

        Args:
            path: qa/ ファイルのパス。

        Returns:
            パースされた QADocument。

        Raises:
            FileNotFoundError: ファイルが存在しない場合。
        """
        if not path.exists():
            raise FileNotFoundError(f"QA ファイルが見つかりません: {path}")
        content = path.read_text(encoding="utf-8")
        return QAMerger.parse_qa_content(content)

    @staticmethod
    def parse_qa_content(content: str) -> QADocument:
        """Markdown 文字列から QADocument をパースする。

        列数が可変（追加列がある場合も対応）なため、ヘッダー行から
        列名を動的に解決してインデックスを決定する。

        Args:
            content: Markdown 形式の QA 質問票テキスト。

        Returns:
            パースされた QADocument。
        """
        doc = QADocument()
        lines = content.splitlines()
        header_pattern = re.compile(r"^\*\*(.+?)\*\*\s*:\s*(.*)$")

        # タイトル（最初の # 見出し）
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                doc.title = stripped[2:].strip()
                break

        # ヘッダーフィールド（**キー**: 値 パターン）
        last_header_idx = -1
        for i, line in enumerate(lines):
            m = header_pattern.match(line.strip())
            if m:
                key = m.group(1).strip()
                value = m.group(2).strip()
                doc.header_fields.append((key, value))
                last_header_idx = i
                if key == "状態":
                    doc.status = value
                elif key == "推論許可":
                    doc.inference_permission = value

        # プレアンブル: ヘッダー直後の --- 以降、最初の ## セクションまでの文字列
        if last_header_idx >= 0:
            preamble_lines: List[str] = []
            found_separator = False
            for line in lines[last_header_idx + 1:]:
                stripped = line.strip()
                if stripped == "---" and not found_separator:
                    found_separator = True
                    continue
                if found_separator:
                    if stripped.startswith("## "):
                        break
                    preamble_lines.append(line)
            doc.preamble = "\n".join(preamble_lines).strip()

        # テーブル検出: | No. | と | 質問 | を含む行をヘッダーとして検出
        table_start_idx = None
        for i, line in enumerate(lines):
            if "|" in line and "No." in line and "質問" in line:
                table_start_idx = i
                break

        if table_start_idx is not None:
            header_line = lines[table_start_idx]
            header_cells = _split_table_row(header_line)

            # ヘッダー行から列名→インデックスのマッピングを構築
            col_map: Dict[str, int] = {
                cell.strip(): idx for idx, cell in enumerate(header_cells)
            }
            idx_no = col_map.get("No.")
            idx_question = col_map.get("質問")
            idx_choices = col_map.get("選択肢")
            idx_default = col_map.get("デフォルトの回答案")
            idx_reason = col_map.get("選択理由")
            idx_user = col_map.get("ユーザー回答")

            # No. と 質問 の両方が見つかった場合のみテーブルをパース
            if idx_no is not None and idx_question is not None:
                for line in lines[table_start_idx + 1:]:
                    stripped = line.strip()
                    if not stripped.startswith("|"):
                        break
                    # セパレータ行（|---|---|...）をスキップ
                    if re.match(r"^\|[\s\-|]+\|$", stripped):
                        continue

                    cells = _split_table_row(stripped)
                    # 最低限 No. と 質問 の列が存在すること
                    if len(cells) <= max(idx_no, idx_question):
                        continue

                    no_str = cells[idx_no].strip()
                    try:
                        no = int(no_str)
                    except ValueError:
                        continue

                    def _cell(idx: Optional[int]) -> str:
                        if idx is None or idx >= len(cells):
                            return ""
                        return cells[idx].strip()

                    question = _cell(idx_question)
                    choices_raw = _cell(idx_choices)
                    default_answer = _cell(idx_default)
                    reason = _cell(idx_reason)
                    user_answer: Optional[str] = None
                    if idx_user is not None:
                        raw = _cell(idx_user)
                        user_answer = raw or None

                    choices = QAMerger._parse_choices(choices_raw)
                    doc.questions.append(QAQuestion(
                        no=no,
                        question=question,
                        choices=choices,
                        default_answer=default_answer,
                        reason=reason,
                        user_answer=user_answer,
                    ))

        # その他セクションを raw_sections に保存（## で始まるセクション）
        current_section: Optional[str] = None
        section_lines: List[str] = []
        for line in lines:
            if line.startswith("## "):
                if current_section is not None:
                    doc.raw_sections[current_section] = "\n".join(section_lines).strip()
                current_section = line[3:].strip()
                section_lines = []
            elif current_section is not None:
                section_lines.append(line)
        if current_section is not None:
            doc.raw_sections[current_section] = "\n".join(section_lines).strip()

        return doc

    @staticmethod
    def _parse_choices(choices_raw: str) -> List[Choice]:
        """選択肢文字列 `A) xxx / B) xxx` を List[Choice] に変換する。

        Args:
            choices_raw: 選択肢文字列（例: "A) 別サービス維持 / B) 統合"）。

        Returns:
            List[Choice]。
        """
        choices: List[Choice] = []
        if not choices_raw:
            return choices

        # A) xxx / B) xxx / C) xxx パターンを分割
        # パターン: 大文字1文字 + ) + テキスト（次の選択肢 " / X)" の直前まで）
        parts = re.split(r"\s*/\s*(?=[A-Z]\))", choices_raw)
        for part in parts:
            m = re.match(r"^([A-Z])\)\s*(.*)", part.strip())
            if m:
                choices.append(Choice(label=m.group(1), text=m.group(2).strip()))
        return choices

    # ------------------------------------------------------------------
    # 回答パース
    # ------------------------------------------------------------------

    @staticmethod
    def parse_answers(answer_text: str) -> Dict[int, str]:
        """回答テキストを解析して {質問番号: 選択肢ラベル} の辞書を返す。

        入力形式:
            # コメント行（無視）
            1: A
            2: B
            3: C

        Args:
            answer_text: "番号: 選択肢" 形式のテキスト。

        Returns:
            {int: str} の辞書（例: {1: "A", 2: "B"}）。
        """
        answers: Dict[int, str] = {}
        for line in answer_text.splitlines():
            stripped = line.strip()
            # コメント行・空行をスキップ
            if not stripped or stripped.startswith("#"):
                continue
            # "番号: 選択肢" パターン（例: "1: A" または "1: A) テキスト"）
            m = re.match(r"^(\d+)\s*:\s*([A-Za-z])", stripped)
            if m:
                no = int(m.group(1))
                label = m.group(2).upper()
                answers[no] = label
        return answers

    # ------------------------------------------------------------------
    # マージ
    # ------------------------------------------------------------------

    @staticmethod
    def merge_answers(
        doc: QADocument,
        answers: Dict[int, str],
        use_defaults: bool = False,
    ) -> QADocument:
        """ユーザー回答を QADocument にマージする。

        Args:
            doc: パース済みの QADocument。
            answers: {質問番号: 選択肢ラベル} の辞書。
            use_defaults: True の場合、全問デフォルト回答を採用する。

        Returns:
            マージ済みの QADocument（新しいオブジェクト）。
        """
        merged = copy.deepcopy(doc)

        for q in merged.questions:
            if use_defaults:
                # デフォルト回答をそのまま採用
                q.user_answer = q.default_answer
            elif q.no in answers:
                label = answers[q.no]
                # 選択肢ラベルに対応するテキストを探す
                matched_choice = next(
                    (c for c in q.choices if c.label.upper() == label.upper()), None
                )
                if matched_choice:
                    q.user_answer = f"{matched_choice.label}) {matched_choice.text}"
                else:
                    # ラベルのみ（選択肢が見つからない場合）
                    q.user_answer = label
            else:
                # 未回答はデフォルト回答を採用
                q.user_answer = q.default_answer

        # 状態を更新:
        # - 推論許可あり + use_defaults → 「推論補完済み」
        # - それ以外 → 「回答済み」
        if use_defaults and merged.inference_permission == "あり":
            merged.status = "推論補完済み"
        else:
            merged.status = "回答済み"

        # header_fields の状態も更新
        merged.header_fields = [
            (k, merged.status if k == "状態" else v)
            for k, v in merged.header_fields
        ]

        return merged

    # ------------------------------------------------------------------
    # レンダリング
    # ------------------------------------------------------------------

    @staticmethod
    def render_merged(doc: QADocument) -> str:
        """マージ済み QADocument を 6 列 Markdown として生成する。

        プレアンブル（ヘッダーフィールドと最初のセクション見出しの間の文章）を
        保持して出力する。

        Args:
            doc: マージ済みの QADocument。

        Returns:
            Markdown 文字列。
        """
        lines: List[str] = []

        # タイトル
        if doc.title:
            lines.append(f"# {doc.title}")
            lines.append("")

        # ヘッダーフィールド
        for key, value in doc.header_fields:
            lines.append(f"**{key}**: {value}")
        if doc.header_fields:
            lines.append("")
            lines.append("---")
            lines.append("")

        # プレアンブル（ヘッダー後・セクション前の文章）
        if doc.preamble:
            lines.append(doc.preamble)
            lines.append("")

        # 質問項目セクション
        if doc.questions:
            lines.append("## 質問項目")
            lines.append("")
            # 6 列テーブルヘッダー
            lines.append("| No. | 質問 | 選択肢 | デフォルトの回答案 | 選択理由 | ユーザー回答 |")
            lines.append("|-----|------|--------|-------------------|----------|------------|")

            for q in doc.questions:
                # セルの | をエスケープ
                def esc(s: str) -> str:
                    return s.replace("|", "&#124;")

                no = str(q.no)
                question = esc(q.question)
                # 選択肢を再構築
                if q.choices:
                    choices_str = " / ".join(
                        f"{c.label}) {c.text}" for c in q.choices
                    )
                else:
                    choices_str = ""
                choices_str = esc(choices_str)
                default = esc(q.default_answer)
                reason = esc(q.reason)
                user_ans = esc(q.user_answer or "")

                lines.append(
                    f"| {no} | {question} | {choices_str} | {default} | {reason} | {user_ans} |"
                )

        # その他セクション
        for section_name, section_content in doc.raw_sections.items():
            # 質問項目セクションは既に出力済みなのでスキップ
            if section_name == "質問項目":
                continue
            lines.append("")
            lines.append(f"## {section_name}")
            if section_content:
                lines.append("")
                lines.append(section_content)

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    @staticmethod
    def save_merged(content: str, path: Path, max_retries: int = 3) -> bool:
        """マージ済みコンテンツをファイルに保存する。

        一時ファイルへの書き込み → read-back 検証 → os.replace() によるアトミック rename
        パターンを採用する。クラッシュ時にも半壊ファイルが残らない。
        各リトライごとに tempfile.mkstemp で一意な一時ファイル名を生成するため、
        同一プロセス内の並列スレッドからの呼び出しでも衝突しない。

        並列安全性:
          - 各ステップは ``qa/{step_id}-qa-merged.md`` という固有のファイルパスを
            使用するため、並列実行時も同一 ``path`` への同時書き込みは発生しない。
          - 一時ファイルは ``tempfile.mkstemp()`` でリトライごとに一意な名前を
            生成するため、同一プロセス内のスレッド並列でも衝突しない。

        Args:
            content: 保存する Markdown コンテンツ。
            path: 保存先ファイルパス。
            max_retries: 最大リトライ回数（デフォルト: 3）。

        Returns:
            True = 成功, False = 失敗。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        for _ in range(max_retries):
            tmp_path: Optional[Path] = None
            try:
                fd, tmp_name = tempfile.mkstemp(
                    dir=path.parent, prefix=path.stem + ".", suffix=".tmp"
                )
                tmp_path = Path(tmp_name)
                try:
                    with os.fdopen(fd, "wb") as tmp_f:
                        tmp_f.write(encoded)
                except Exception:
                    # fd は os.fdopen が閉じる。ファイルはクリーンアップする。
                    tmp_path.unlink(missing_ok=True)
                    raise
                written = tmp_path.read_text(encoding="utf-8")
                if written == content:
                    os.replace(str(tmp_path), str(path))  # アトミックな rename
                    return True
                tmp_path.unlink(missing_ok=True)
            except OSError:
                if tmp_path is not None:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        return False

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    @staticmethod
    def generate_consolidated_path(qa_path: Path) -> Path:
        """統合ドキュメントのパスを生成する。

        既に `-consolidated` で終わるファイル名の場合は二重付与しない。

        Args:
            qa_path: 元の qa/ ファイルパス（例: qa/foo.md）。

        Returns:
            統合ドキュメントのパス（例: qa/foo-consolidated.md）。
        """
        stem = qa_path.stem
        # 既に -consolidated で終わっている場合は二重付与しない
        if stem.endswith("-consolidated"):
            return qa_path
        return qa_path.parent / f"{stem}-consolidated.md"

    @staticmethod
    def find_qa_files(qa_dir: Path, pattern: str = "*.md") -> List[Path]:
        """qa/ ディレクトリから質問票ファイルをリストアップする。

        `-consolidated.md` で終わるファイルは除外する。

        Args:
            qa_dir: 検索対象ディレクトリ。
            pattern: glob パターン（デフォルト: "*.md"）。

        Returns:
            ファイルパスのリスト（ソート済み）。
        """
        return sorted(
            p for p in qa_dir.glob(pattern)
            if not p.name.endswith("-consolidated.md")
        )


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------

def _split_table_row(line: str) -> List[str]:
    """Markdown テーブル行をセルに分割する。

    先頭・末尾の連続する `|` をすべて除去してから `|` で分割し、
    各セルの前後空白もトリムする。LLM 出力でありがちな二重パイプ（`||`）にも対応。

    Args:
        line: Markdown テーブル行（例: "| 1 | 質問 | ... |"）。

    Returns:
        セルのリスト（各セルの前後空白はトリム済み）。
    """
    stripped = line.strip().lstrip("|").rstrip("|")
    return [cell.strip() for cell in stripped.split("|")]

