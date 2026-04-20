"""qa_merger.py — QA 質問票マージエンジン

QA 質問票ファイル（`qa/` 配下）を解析し、ユーザー回答をマージして
テーブル形式で保存する。統合ドキュメントのパス生成もサポートする。

対応フォーマット:
  - テーブル形式（旧形式・新形式ともに対応）:
    | No. | [重要度] | [分類項目] | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | [ユーザー回答] |
  - 構造化テキスト形式（新形式）:
    [Q01]
    - 分類項目: ...
    - 重要度: ...
    - 質問文: ...

ファイル構造:
    # タイトル

    **状態**: 回答待ち
    **推論許可**: なし
    ...
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
# 定数
# ---------------------------------------------------------------------------

# 数字ラベル（1./2./3.）→ 英字ラベル（A/B/C...）変換テーブル
_NUM_TO_ALPHA: Dict[str, str] = {str(i): chr(64 + i) for i in range(1, 27)}


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
    default_answer: str = ""       # 既定値候補
    reason: str = ""               # 既定値候補の理由
    user_answer: Optional[str] = None
    priority: str = ""             # 重要度（最重要/高/中/低）
    category: str = ""             # 分類項目
    impact_if_unanswered: str = "" # 未回答のまま進めた場合の影響


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

            def _col_idx(primary: str, fallback: str) -> Optional[int]:
                """列名→インデックスを取得する。新用語優先で旧用語にフォールバック。
                インデックス0の falsy 誤判定を防ぐため None チェーンを使用する。
                """
                v = col_map.get(primary)
                return v if v is not None else col_map.get(fallback)

            # 旧用語・新用語の両方に対応
            idx_default = _col_idx("既定値候補", "デフォルトの回答案")
            idx_reason = _col_idx("既定値候補の理由", "選択理由")
            idx_user = col_map.get("ユーザー回答")

            # 新形式の列名
            idx_priority = col_map.get("重要度")
            idx_category = col_map.get("分類項目")
            idx_impact = _col_idx("未回答のまま進めた場合の影響", "未回答時の影響")

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
                        priority=_cell(idx_priority),
                        category=_cell(idx_category),
                        impact_if_unanswered=_cell(idx_impact),
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

        # 構造化テキスト形式フォールバック（テーブルが見つからない、またはパース失敗の場合）
        if table_start_idx is None or not doc.questions:
            structured_questions = QAMerger._parse_structured_questions(content)
            if structured_questions:
                doc.questions = structured_questions

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

    @staticmethod
    def _normalize_structured_question_markers(content: str) -> str:
        """[Q01] 見出しの Markdown 装飾ゆらぎを正規化する。"""
        return re.sub(r"\*{1,3}(\[Q\d+\])\*{1,3}", r"\1", content)

    @staticmethod
    def _parse_structured_questions(content: str) -> List[QAQuestion]:
        """新形式の構造化質問票（[Q01]形式）をパースする。

        LLM 出力のゆらぎ（空行・スペース・コロンの全角/半角）に対応する。
        選択肢ラベルは英字（A/B/C...）を維持する。
        数字ラベル（1./2./3.）の場合は英字に変換する。
        """
        content = QAMerger._normalize_structured_question_markers(content)
        questions: List[QAQuestion] = []
        blocks = re.split(r"^\[Q(\d+)\]\s*$", content, flags=re.MULTILINE)
        for i in range(1, len(blocks), 2):
            no = int(blocks[i])
            body = blocks[i + 1] if i + 1 < len(blocks) else ""
            q = QAQuestion(no=no, question="")

            def _match_field(line_stripped: str, field_name: str) -> Optional[str]:
                m = re.match(
                    rf"^-\s*{re.escape(field_name)}\s*[:：]\s*(.*)",
                    line_stripped,
                )
                return m.group(1).strip() if m else None

            collecting_choices = False
            for line in body.splitlines():
                stripped = line.strip()

                val = _match_field(stripped, "質問文")
                if val is not None:
                    q.question = val
                    collecting_choices = False
                    continue

                val = _match_field(stripped, "重要度")
                if val is not None:
                    q.priority = val
                    collecting_choices = False
                    continue

                val = _match_field(stripped, "分類項目")
                if val is not None:
                    q.category = val
                    collecting_choices = False
                    continue

                val = _match_field(stripped, "確認したいこと")
                if val is not None:
                    if not q.question:
                        q.question = val
                    collecting_choices = False
                    continue

                val = _match_field(stripped, "未回答時の既定値候補")
                if val is not None:
                    q.default_answer = val
                    collecting_choices = False
                    continue

                val = _match_field(stripped, "既定値候補の理由")
                if val is not None:
                    q.reason = val
                    collecting_choices = False
                    continue

                val = _match_field(stripped, "未回答のまま進めた場合の影響")
                if val is not None:
                    q.impact_if_unanswered = val
                    collecting_choices = False
                    continue

                if _match_field(stripped, "選択肢") is not None:
                    collecting_choices = True
                    continue

                if collecting_choices:
                    m_alpha = re.match(r"^([A-Za-z])[.):\s]\s*(.*)", stripped)
                    if m_alpha:
                        q.choices.append(Choice(
                            label=m_alpha.group(1).upper(),
                            text=m_alpha.group(2).strip(),
                        ))
                        continue
                    m_num = re.match(r"^(\d+)[.):\s]\s*(.*)", stripped)
                    if m_num:
                        alpha_label = _NUM_TO_ALPHA.get(m_num.group(1), m_num.group(1))
                        q.choices.append(Choice(
                            label=alpha_label,
                            text=m_num.group(2).strip(),
                        ))
                        continue
                    if stripped and not stripped.startswith("-"):
                        collecting_choices = False

            if q.question:
                questions.append(q)
        return questions

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
        """マージ済み QADocument を Markdown テーブルとして生成する。

        新フィールド（priority, category, impact_if_unanswered）がある質問が
        1つでもあれば9列テーブル、なければ6列テーブルを出力する。

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

            # 新フィールドの有無に応じて列数を動的決定
            use_extended = any(
                q.priority or q.category or q.impact_if_unanswered
                for q in doc.questions
            )

            if use_extended:
                # 9列テーブルヘッダー（未回答のまま進めた場合の影響を含む）
                lines.append("| No. | 重要度 | 分類項目 | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | 未回答のまま進めた場合の影響 | ユーザー回答 |")
                lines.append("|-----|--------|----------|------|--------|-----------|----------------|------------------------------|------------|")
            else:
                # 6列テーブルヘッダー
                lines.append("| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | ユーザー回答 |")
                lines.append("|-----|------|--------|-----------|----------------|------------|")

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

                if use_extended:
                    priority = esc(q.priority)
                    category = esc(q.category)
                    impact = esc(q.impact_if_unanswered)
                    lines.append(
                        f"| {no} | {priority} | {category} | {question} | {choices_str} | {default} | {reason} | {impact} | {user_ans} |"
                    )
                else:
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
