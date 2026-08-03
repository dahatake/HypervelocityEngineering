"""hve.gui.timezones — `<run-id>` 生成用タイムゾーン選択肢。

GUI 設定画面 C1「基本設定」の `run_id_timezone` コンボに表示する
IANA タイムゾーン名と表示ラベルのリスト。

- 既定値: ``Asia/Tokyo`` (JST)
- 表示ラベルはユーザー視認用。実値は IANA 名 (``zoneinfo`` で解決可能)。
"""

from __future__ import annotations

from typing import List, Tuple

DEFAULT_TIMEZONE = "Asia/Tokyo"

# (IANA 名, 表示ラベル) のタプル。リスト先頭から順に表示する。
TIMEZONE_CHOICES: List[Tuple[str, str]] = [
    ("Asia/Tokyo", "Asia/Tokyo (JST, UTC+9)"),
    ("Asia/Seoul", "Asia/Seoul (KST, UTC+9)"),
    ("Asia/Shanghai", "Asia/Shanghai (CST, UTC+8)"),
    ("Asia/Singapore", "Asia/Singapore (UTC+8)"),
    ("Asia/Hong_Kong", "Asia/Hong_Kong (UTC+8)"),
    ("Asia/Taipei", "Asia/Taipei (UTC+8)"),
    ("Asia/Bangkok", "Asia/Bangkok (UTC+7)"),
    ("Asia/Jakarta", "Asia/Jakarta (UTC+7)"),
    ("Asia/Kolkata", "Asia/Kolkata (IST, UTC+5:30)"),
    ("Asia/Dubai", "Asia/Dubai (UTC+4)"),
    ("Europe/Moscow", "Europe/Moscow (UTC+3)"),
    ("Europe/Istanbul", "Europe/Istanbul (UTC+3)"),
    ("Africa/Cairo", "Africa/Cairo (UTC+2)"),
    ("Europe/Berlin", "Europe/Berlin (CET/CEST)"),
    ("Europe/Paris", "Europe/Paris (CET/CEST)"),
    ("Europe/Rome", "Europe/Rome (CET/CEST)"),
    ("Europe/Madrid", "Europe/Madrid (CET/CEST)"),
    ("Europe/Amsterdam", "Europe/Amsterdam (CET/CEST)"),
    ("Europe/London", "Europe/London (GMT/BST)"),
    ("Europe/Dublin", "Europe/Dublin (GMT/IST)"),
    ("UTC", "UTC"),
    ("Atlantic/Azores", "Atlantic/Azores (UTC-1)"),
    ("America/Sao_Paulo", "America/Sao_Paulo (UTC-3)"),
    ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos_Aires (UTC-3)"),
    ("America/New_York", "America/New_York (EST/EDT)"),
    ("America/Toronto", "America/Toronto (EST/EDT)"),
    ("America/Chicago", "America/Chicago (CST/CDT)"),
    ("America/Denver", "America/Denver (MST/MDT)"),
    ("America/Los_Angeles", "America/Los_Angeles (PST/PDT)"),
    ("America/Anchorage", "America/Anchorage (AKST/AKDT)"),
    ("Pacific/Honolulu", "Pacific/Honolulu (HST, UTC-10)"),
    ("Pacific/Auckland", "Pacific/Auckland (NZST/NZDT)"),
    ("Australia/Sydney", "Australia/Sydney (AEST/AEDT)"),
]
