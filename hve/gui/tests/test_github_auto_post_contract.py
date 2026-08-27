"""FR-GUI-36: GitHub自動進捗Postの設定境界RED契約。"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

import pytest

from hve.config import SDKConfig
from hve.gui import settings_apply, settings_store
from hve.gui.orchestrate_args import OrchestrateArgs

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


class TestAutoPostSetting:
    def test_default_is_off(self) -> None:
        assert settings_store.defaults()["options"]["github_auto_post_target"] == "off"

    def test_c5_mapping_owns_the_setting(self) -> None:
        assert settings_apply._SECTION_FIELDS["C5"]["github_auto_post_target"] == (
            "github_auto_post_target"
        )

    def test_widget_offers_only_four_targets(self, qapp) -> None:
        from hve.gui.page_options import _C5IssuePR

        widget = _C5IssuePR()
        field_name = "".join(("github", "_auto", "_post", "_target"))
        assert hasattr(widget, field_name)
        combo: Any = vars(widget)[field_name]
        values = [
            combo.itemData(index)
            for index in range(combo.count())
        ]
        assert values == ["off", "issue", "pr", "both"]

    def test_setting_does_not_enter_sdk_config(self) -> None:
        assert "github_auto_post_target" not in {
            field.name for field in dataclasses.fields(SDKConfig)
        }

    def test_setting_does_not_enter_orchestrator_args(self) -> None:
        assert "github_auto_post_target" not in {
            field.name for field in dataclasses.fields(OrchestrateArgs)
        }
