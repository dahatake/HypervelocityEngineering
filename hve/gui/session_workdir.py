"""hve.gui.session_workdir — GUI セッション毎の作業ディレクトリ管理。

Issue-gui-session-workdir-isolation T3 で導入。

目的:
  - GUI MainWindow 1 インスタンス = 1 セッションとして
    `<repo>/work/gui-runs/<session_run_id>/` を作成し、
    子プロセスに `HVE_WORK_ROOT` / `HVE_GUI_SESSION_ID` env で渡す。
  - 既存 `work/Issue-*/` 群（CLI 由来・過去 GUI 由来）との干渉を物理的に排除する。

session_run_id:
  - `gui-{hve.config.generate_run_id()}` 形式（既存 ID 生成器を流用）。
  - 例: ``"gui-20260521T074921-a1b2c3"``。

cleanup_policy:
  - ``"keep"``    : 何もしない (既定)。
  - ``"archive"`` : ``work/gui-runs/.archive/<session_run_id>.zip`` に zip 化して元 dir 削除。
  - ``"purge"``   : ``work_root`` を rmtree 削除。

参考:
  - copilot-instructions.md §0.5 ("CLI セッション起点モード")
  - hve/split_fork.py `resolve_work_root` (HVE_WORK_ROOT を優先参照)
"""
from __future__ import annotations

import logging
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal

try:
    from hve.config import generate_run_id
except ImportError:  # pragma: no cover - script execution path
    from config import generate_run_id  # type: ignore[no-redef]


__all__ = [
    "GuiSessionWorkdir",
    "CleanupPolicy",
    "ARCHIVE_DIRNAME",
    "GUI_RUNS_DIRNAME",
    "SESSION_ID_PREFIX",
]

logger = logging.getLogger(__name__)

CleanupPolicy = Literal["keep", "archive", "purge"]

ARCHIVE_DIRNAME: str = ".archive"
GUI_RUNS_DIRNAME: str = "gui-runs"
SESSION_ID_PREFIX: str = "gui-"


def _is_valid_policy(policy: str) -> bool:
    return policy in ("keep", "archive", "purge")


@dataclass(frozen=True)
class GuiSessionWorkdir:
    """GUI セッション 1 つに対応する作業ディレクトリと env オーバーライド。

    Attributes:
        session_run_id: ``gui-<generate_run_id()>`` 形式の一意 ID。
        work_root: ``<repo>/work/gui-runs/<session_run_id>/`` の絶対 Path。
        cleanup_policy: セッション終了時の挙動。
        had_env_override: 起動時に既に `HVE_WORK_ROOT` が env にセットされていたか
            （Q16: WARNING ログ出力のために保持）。
    """

    session_run_id: str
    work_root: Path
    cleanup_policy: str = "keep"
    had_env_override: bool = False

    # -----------------------------------------------------------------
    # factory
    # -----------------------------------------------------------------

    @classmethod
    def create(
        cls,
        repo_root: Path,
        *,
        cleanup_policy: str = "keep",
    ) -> "GuiSessionWorkdir":
        """新しいセッション ID を採番し work_root を作成して返す。

        Args:
            repo_root: リポジトリルート（通常 ``Path(__file__).resolve().parents[2]``）。
            cleanup_policy: ``"keep" / "archive" / "purge"``。不正値は ``"keep"`` に
                フォールバックし WARNING を出す。

        Returns:
            初期化済み ``GuiSessionWorkdir`` インスタンス。
        """
        policy = cleanup_policy if _is_valid_policy(cleanup_policy) else "keep"
        if policy != cleanup_policy:
            logger.warning(
                "GuiSessionWorkdir: 不正な cleanup_policy=%r を keep にフォールバック",
                cleanup_policy,
            )

        session_run_id = f"{SESSION_ID_PREFIX}{generate_run_id()}"
        work_root = (
            repo_root.resolve() / "work" / GUI_RUNS_DIRNAME / session_run_id
        )
        work_root.mkdir(parents=True, exist_ok=True)

        had_override = bool(os.environ.get("HVE_WORK_ROOT"))
        if had_override:
            logger.warning(
                "GuiSessionWorkdir: 既存環境変数 HVE_WORK_ROOT=%r を "
                "GUI セッション用パス %r で上書きします (Q16)",
                os.environ.get("HVE_WORK_ROOT"),
                str(work_root),
            )

        return cls(
            session_run_id=session_run_id,
            work_root=work_root,
            cleanup_policy=policy,
            had_env_override=had_override,
        )

    # -----------------------------------------------------------------
    # env propagation
    # -----------------------------------------------------------------

    def env_overrides(self) -> Dict[str, str]:
        """子プロセスに注入すべき環境変数を返す (Q10: 2 種)。"""
        return {
            "HVE_WORK_ROOT": str(self.work_root),
            "HVE_GUI_SESSION_ID": self.session_run_id,
        }

    def apply_to_env(self, env: Dict[str, str]) -> Dict[str, str]:
        """与えられた env dict に overrides を適用した新 dict を返す。"""
        new_env = dict(env)
        new_env.update(self.env_overrides())
        return new_env

    # -----------------------------------------------------------------
    # cleanup
    # -----------------------------------------------------------------

    def cleanup(self) -> None:
        """``cleanup_policy`` に従って ``work_root`` を後処理する。

        例外は内部で握り潰し、WARNING ログのみ出す（GUI 終了処理を止めないため）。
        """
        try:
            if not self.work_root.exists():
                return
            if self.cleanup_policy == "keep":
                return
            if self.cleanup_policy == "purge":
                self._purge()
                return
            if self.cleanup_policy == "archive":
                self._archive()
                return
        except Exception as exc:  # pragma: no cover - 防御的
            logger.warning(
                "GuiSessionWorkdir.cleanup: policy=%s で例外発生 (work_root=%s): %s",
                self.cleanup_policy,
                self.work_root,
                exc,
            )

    def _purge(self) -> None:
        shutil.rmtree(self.work_root, ignore_errors=False)

    def _archive(self) -> None:
        archive_root = self.work_root.parent / ARCHIVE_DIRNAME
        archive_root.mkdir(parents=True, exist_ok=True)
        zip_path = archive_root / f"{self.session_run_id}.zip"

        # 既存 zip があれば上書き（同一 session_run_id は理論上発生しないが防御）
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in self.work_root.rglob("*"):
                if path.is_file():
                    # zip 仕様 (PKZIP APPNOTE 4.4.17.1) は forward slash のみ規定。
                    # Windows のバックスラッシュ区切りで格納すると Linux/macOS で
                    # ディレクトリが認識されないため as_posix() で正規化する。
                    arcname = path.relative_to(self.work_root).as_posix()
                    zf.write(path, arcname)

        shutil.rmtree(self.work_root, ignore_errors=False)
