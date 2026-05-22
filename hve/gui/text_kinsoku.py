"""hve.gui.text_kinsoku — フッタ/ステータス表示用の小ヘルパ。

GUI Footer は多項目を 1 つの ``QLabel`` (wordWrap=True) で表示するため、
- 「項目名+値」は途中で改行されないよう ``&nbsp;`` 化する
- 区切り `|` の前後で改行が起きやすいよう **ゼロ幅スペース (ZWSP, U+200B)** を挿入する
- CJK 行頭/行末禁則文字が行頭/行末に来ないよう調整する
というユーティリティを提供する。

最小限の実装。Qt の ``QTextOption`` ベースのレイアウトには介入しない。
"""

from __future__ import annotations

from typing import Iterable, Optional

# Zero-Width Space。Qt の wordWrap は ZWSP を改行候補として扱う。
ZWSP = "\u200b"

# Non-breaking space (HTML entity)
NBSP = "&nbsp;"

# 行頭禁則 (これらの文字は行頭に来てはいけない)
_KINSOKU_LINE_START = set("、。，．・：；！？）］｝〕〉》」』】〗〙〛々ゝゞ・ー…")
# 行末禁則 (これらの文字は行末に来てはいけない)
_KINSOKU_LINE_END = set("（［｛〔〈《「『【〖〘〚")


def wrap_nowrap_unit(label: str, value: str, *, label_color: str, value_color: str) -> str:
    """「項目名: 値」を 1 単位として途中で改行されないようにする HTML 断片を返す。

    内部のスペースは ``&nbsp;`` 化する (HTML 表示時は空白を 1 つに圧縮するため、
    視覚的なずれを防止する効果もある)。
    """
    safe_label = _escape(label).replace(" ", NBSP)
    safe_value = _escape(value).replace(" ", NBSP)
    # white-space: nowrap でも HTML 内空白は折り返し候補になりうるため &nbsp; 併用
    return (
        f"<span style='white-space:nowrap; color:{label_color}; font-weight:bold;'>"
        f"{safe_label}:</span>{NBSP}"
        f"<span style='white-space:nowrap; color:{value_color};'>{safe_value}</span>"
    )


def join_items(items: Iterable[str], *, separator_color: str = "#999999") -> str:
    """nowrap な単位 HTML 群を区切り ``|`` で結合する。

    区切りの前後に ZWSP を挿入し、長くなった場合に区切り位置で自然に折り返される
    ようにする。
    """
    sep = (
        f"{ZWSP}<span style='color:{separator_color};'>{NBSP}|{NBSP}</span>{ZWSP}"
    )
    return sep.join(items)


def apply_cjk_kinsoku(text: str) -> str:
    """ごく簡易な行頭禁則処理を行う。

    現状では、改行候補となる ZWSP の直後に行頭禁則文字が来る場合、その ZWSP を
    削除して同じ行に留まるようにする。完全な禁則処理は QTextLayout 等で行う必要が
    あるが、ここでは Footer 用途で十分なヒューリスティック実装に留める。
    """
    if not text or ZWSP not in text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == ZWSP and i + 1 < n and text[i + 1] in _KINSOKU_LINE_START:
            # ZWSP をスキップして改行候補を潰す
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def format_elapsed(seconds: float) -> str:
    """秒数を ``HH:MM:SS`` に整形する。負値・NaN は ``00:00:00``。"""
    try:
        v = max(0, int(seconds))
    except (TypeError, ValueError):
        return "00:00:00"
    h = v // 3600
    m = (v % 3600) // 60
    s = v % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_cost(
    cost_usd: Optional[float],
    cost_jpy: Optional[float],
    *,
    currency: str = "auto",
    locale: str = "ja",
) -> str:
    """累積コストを表示用文字列に整形する。

    - 値が ``None`` (= 料金計算不可) の場合は ``"-"`` を返し**捏造しない**。
    - currency:
        - ``"both"`` または ``"auto"`` (locale=="ja") → ``"$X.XXXX (¥Y)"``
        - ``"usd"``                                    → ``"$X.XXXX"``
        - ``"jpy"``                                    → ``"¥Y"``
    """
    if cost_usd is None and cost_jpy is None:
        return "-"

    mode = (currency or "auto").lower()
    if mode == "auto":
        mode = "both" if (locale or "").lower().startswith("ja") else "usd"

    def _usd() -> str:
        if cost_usd is None:
            return "-"
        # 細かい金額も視認できるよう小数 4 桁。1 ドル超は 2 桁。
        if abs(cost_usd) >= 1.0:
            return f"${cost_usd:.2f}"
        return f"${cost_usd:.4f}"

    def _jpy() -> str:
        if cost_jpy is None:
            return "-"
        # 円は整数で十分。マイナス値は捏造禁止により発生しない想定。
        return f"¥{int(round(cost_jpy)):,}"

    if mode == "usd":
        return _usd()
    if mode == "jpy":
        return _jpy()
    # both
    return f"{_usd()} ({_jpy()})"


def _escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
