"""[REMOVED] 旧 ActivityStatusWidget を含む Phase 2 統合テスト

DagStatusWidget への置換により本テストは無効化されている。
新ウィジェットのテストは test_dag_status_widget.py / test_dag_layout.py
および test_workbench_state_prefix.py を参照。
"""
from __future__ import annotations

import pytest

pytest.skip(
    "ActivityStatusWidget removed; replaced by DagStatusWidget",
    allow_module_level=True,
)
