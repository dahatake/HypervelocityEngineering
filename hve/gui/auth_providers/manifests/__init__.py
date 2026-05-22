"""hve.gui.auth_providers.manifests — Plugin / MCP 認証フロー manifest ローダ。

設計:
    - 各 manifest は YAML ファイル (`*.yml` または `*.yaml`)。
    - 同梱 manifest は本パッケージ配下に置く。ユーザー追加 manifest は
      ``$HVE_AUTH_MANIFESTS_DIR`` (任意) のパスから追加で読み込む。
    - プロバイダ識別子 (例 ``"mcp:azure"``, ``"workiq"``, ``"external_cli"``) と
      補助情報 (mcp_server_name / cli_url) で **最初に一致した manifest** を返す。
    - manifest が存在しない場合は ``None`` を返す (呼び出し側で既存挙動へフォールバック)。

YAML スキーマ (キーは全て snake_case):
    id: str (必須)                    # manifest 一意 ID
    display_name: str (任意)          # UI 表示名
    match:                             # 最低 1 つは必須
      mcp_server_name_regex: str (任意)
      provider_id_regex: str (任意)
      cli_url_regex: str (任意)
    pre_auth_commands:                 # 任意。順次 PTY 実行する前提コマンド
      - argv: list[str] (必須)
        success_regex: str (任意)
        failure_regex: str (任意)
        timeout: float (任意, 既定 600)
    main_command:                      # 任意。最後に走らせる主コマンド
      argv: list[str]
      success_regex: str (任意)
      failure_regex: str (任意)
      timeout: float (任意, 既定 600)
    copilot_seed_prompt: str (任意)    # main_command が無い場合に copilot CLI へ流す
    success_regex: str (任意)          # 全体としての success パターン (main_command 用)
    failure_regex: str (任意)
    timeout_total: float (任意, 既定 900)
    notes_md: str (任意)               # UI に表示するユーザー向け注意書き

セキュリティ:
    - ``argv`` はリスト形式必須 (shell 経由ではない)。
    - regex は事前 ``re.compile`` で構文検証する (起動時失敗を早期検知)。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # type: ignore[import-untyped]

_logger = logging.getLogger(__name__)

__all__ = [
    "ManifestCommand",
    "ManifestMatch",
    "Manifest",
    "ManifestError",
    "load_manifest_for",
    "load_all_manifests",
    "builtin_manifests_dir",
    "user_manifests_dir",
]


class ManifestError(ValueError):
    """manifest のパース / バリデーション失敗。"""


# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestCommand:
    """1 コマンド分の起動仕様 (manifest 由来)。"""

    argv: List[str]
    success_regex: Optional[str] = None
    failure_regex: Optional[str] = None
    timeout: float = 600.0


@dataclass(frozen=True)
class ManifestMatch:
    """プロバイダ → manifest のマッチング規則。"""

    mcp_server_name_regex: Optional[str] = None
    provider_id_regex: Optional[str] = None
    cli_url_regex: Optional[str] = None

    def is_empty(self) -> bool:
        return all(
            v is None
            for v in (
                self.mcp_server_name_regex,
                self.provider_id_regex,
                self.cli_url_regex,
            )
        )

    def matches(
        self,
        *,
        provider_id: Optional[str] = None,
        mcp_server_name: Optional[str] = None,
        cli_url: Optional[str] = None,
    ) -> bool:
        """少なくとも 1 つの非 None 規則が一致したら True。"""
        if self.is_empty():
            return False
        if self.provider_id_regex and provider_id:
            if re.search(self.provider_id_regex, provider_id):
                return True
        if self.mcp_server_name_regex and mcp_server_name:
            if re.search(self.mcp_server_name_regex, mcp_server_name):
                return True
        if self.cli_url_regex and cli_url:
            if re.search(self.cli_url_regex, cli_url):
                return True
        return False


@dataclass(frozen=True)
class Manifest:
    """1 つの認証フロー定義。"""

    id: str
    display_name: Optional[str]
    match: ManifestMatch
    pre_auth_commands: List[ManifestCommand] = field(default_factory=list)
    main_command: Optional[ManifestCommand] = None
    copilot_seed_prompt: Optional[str] = None
    success_regex: Optional[str] = None
    failure_regex: Optional[str] = None
    timeout_total: float = 900.0
    notes_md: Optional[str] = None
    # T1 (Wave 1): 本サーバ/プロバイダ利用時に事前認証が必要か。
    # 既定 True (後方互換)。Microsoft Learn 等の認証不要 MCP は明示的に False。
    auth_required: bool = True
    source_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# パース
# ---------------------------------------------------------------------------


def _require_list_of_str(value: Any, ctx: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ManifestError(f"{ctx}: must be list[str]")
    if not value:
        raise ManifestError(f"{ctx}: must be non-empty")
    return list(value)


def _opt_str(value: Any, ctx: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError(f"{ctx}: must be str")
    return value


def _opt_float(value: Any, ctx: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"{ctx}: must be number") from exc


def _validate_regex(pattern: Optional[str], ctx: str) -> Optional[str]:
    if pattern is None:
        return None
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ManifestError(f"{ctx}: invalid regex: {exc}") from exc
    return pattern


def _parse_command(data: Any, ctx: str) -> ManifestCommand:
    if not isinstance(data, dict):
        raise ManifestError(f"{ctx}: must be mapping")
    argv = _require_list_of_str(data.get("argv"), f"{ctx}.argv")
    return ManifestCommand(
        argv=argv,
        success_regex=_validate_regex(
            _opt_str(data.get("success_regex"), f"{ctx}.success_regex"),
            f"{ctx}.success_regex",
        ),
        failure_regex=_validate_regex(
            _opt_str(data.get("failure_regex"), f"{ctx}.failure_regex"),
            f"{ctx}.failure_regex",
        ),
        timeout=_opt_float(data.get("timeout"), f"{ctx}.timeout", 600.0),
    )


def _parse_manifest(data: Any, *, source: Optional[Path] = None) -> Manifest:
    if not isinstance(data, dict):
        raise ManifestError("root must be mapping")
    mid = data.get("id")
    if not isinstance(mid, str) or not mid:
        raise ManifestError("id: required non-empty string")

    match_raw = data.get("match")
    if not isinstance(match_raw, dict):
        raise ManifestError("match: required mapping")
    match = ManifestMatch(
        mcp_server_name_regex=_validate_regex(
            _opt_str(match_raw.get("mcp_server_name_regex"), "match.mcp_server_name_regex"),
            "match.mcp_server_name_regex",
        ),
        provider_id_regex=_validate_regex(
            _opt_str(match_raw.get("provider_id_regex"), "match.provider_id_regex"),
            "match.provider_id_regex",
        ),
        cli_url_regex=_validate_regex(
            _opt_str(match_raw.get("cli_url_regex"), "match.cli_url_regex"),
            "match.cli_url_regex",
        ),
    )
    if match.is_empty():
        raise ManifestError("match: at least one of mcp_server_name_regex/provider_id_regex/cli_url_regex is required")

    pre_raw = data.get("pre_auth_commands") or []
    if not isinstance(pre_raw, list):
        raise ManifestError("pre_auth_commands: must be list")
    pre_commands = [
        _parse_command(item, f"pre_auth_commands[{i}]")
        for i, item in enumerate(pre_raw)
    ]

    main_raw = data.get("main_command")
    main_command = _parse_command(main_raw, "main_command") if main_raw is not None else None

    # T1 (Wave 1): auth_required を bool として読み取る (既定 True)。
    auth_required_raw = data.get("auth_required", True)
    if not isinstance(auth_required_raw, bool):
        raise ManifestError("auth_required: must be bool")

    return Manifest(
        id=mid,
        display_name=_opt_str(data.get("display_name"), "display_name"),
        match=match,
        pre_auth_commands=pre_commands,
        main_command=main_command,
        copilot_seed_prompt=_opt_str(data.get("copilot_seed_prompt"), "copilot_seed_prompt"),
        success_regex=_validate_regex(
            _opt_str(data.get("success_regex"), "success_regex"), "success_regex"
        ),
        failure_regex=_validate_regex(
            _opt_str(data.get("failure_regex"), "failure_regex"), "failure_regex"
        ),
        timeout_total=_opt_float(data.get("timeout_total"), "timeout_total", 900.0),
        notes_md=_opt_str(data.get("notes_md"), "notes_md"),
        auth_required=auth_required_raw,
        source_path=source,
    )


# ---------------------------------------------------------------------------
# 検索
# ---------------------------------------------------------------------------


def builtin_manifests_dir() -> Path:
    """同梱 manifest のディレクトリ。"""
    return Path(__file__).resolve().parent


def user_manifests_dir() -> Optional[Path]:
    """ユーザー追加 manifest のディレクトリ (環境変数 ``HVE_AUTH_MANIFESTS_DIR``)。"""
    env = os.environ.get("HVE_AUTH_MANIFESTS_DIR")
    if not env:
        return None
    p = Path(env).expanduser()
    return p if p.is_dir() else None


def _iter_manifest_files() -> List[Path]:
    """探索順: builtin → user。同名 id があれば後勝ち (user override)。"""
    results: List[Path] = []
    builtin = builtin_manifests_dir()
    if builtin.is_dir():
        for p in sorted(builtin.iterdir()):
            if p.is_file() and p.suffix.lower() in (".yml", ".yaml") and not p.name.startswith("_README"):
                results.append(p)
    user_dir = user_manifests_dir()
    if user_dir is not None:
        for p in sorted(user_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in (".yml", ".yaml"):
                results.append(p)
    return results


def load_all_manifests() -> List[Manifest]:
    """全 manifest をロードする (パース失敗ファイルは skip し警告を返さない方針)。

    Returns:
        順序は ``_iter_manifest_files`` と同じ (builtin → user)。
        ``_default.yml`` は最後にマッチ判定する慣習 (ID 順ではなくファイル名順)。
    """
    out: List[Manifest] = []
    seen_ids: Dict[str, int] = {}
    for path in _iter_manifest_files():
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            manifest = _parse_manifest(data, source=path)
        except (OSError, yaml.YAMLError, ManifestError) as exc:
            # 1 ファイルの破損が全体を巻き込まないように skip するが、
            # ユーザーがデバッグできるよう warning ログを残す (レビュー No.26)。
            _logger.warning("Skipping invalid manifest %s: %s", path, exc)
            continue
        # 同名 id は後勝ち
        if manifest.id in seen_ids:
            out[seen_ids[manifest.id]] = manifest
        else:
            seen_ids[manifest.id] = len(out)
            out.append(manifest)
    return out


def load_manifest_for(
    *,
    provider_id: Optional[str] = None,
    mcp_server_name: Optional[str] = None,
    cli_url: Optional[str] = None,
) -> Optional[Manifest]:
    """与えられた識別子に対し最初にマッチする manifest を返す。

    マッチ順: ファイル名順 (アンダースコア接頭辞のファイルが先頭 → ``_default.yml``
    を任意の最後の包括マッチとして使えるよう、``_default`` は明示的に最後尾扱い)。
    """
    manifests = load_all_manifests()
    default: Optional[Manifest] = None
    for m in manifests:
        if m.id == "_default":
            default = m
            continue
        if m.match.matches(
            provider_id=provider_id,
            mcp_server_name=mcp_server_name,
            cli_url=cli_url,
        ):
            return m
    if default is not None and default.match.matches(
        provider_id=provider_id,
        mcp_server_name=mcp_server_name,
        cli_url=cli_url,
    ):
        return default
    return None
