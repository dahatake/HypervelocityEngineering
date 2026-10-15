"""外部連携カタログの結合テストの入口（FR-1035 AC-208/209/210、FR-1036 AC-211/212/213、FR-1037 AC-214/215）。

本体は tests/toolkit/test_integrations.py（導入先を模した使い捨てのリポジトリで、verify・rdcheck・next-id・install を
実際に実行する）。tests/toolkit は要求 ID の走査の対象外なので、要求 ID と受入基準 ID をこのファイルに書いて、
要求からテストをたどれるようにする。
"""
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]


# FR-1035 AC-208 AC-209 AC-210 / FR-1036 AC-211 AC-212 AC-213 / FR-1037 AC-214 AC-215
def test_external_integration_catalog_suite_passes():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", str(SOURCE / "tests" / "toolkit" / "test_integrations.py")],
        cwd=SOURCE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


# FR-1038 AC-216 AC-217 / FR-1039 AC-218 AC-219
def test_external_integration_requirements_suite_passes():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", str(SOURCE / "tests" / "toolkit" / "test_integration_requirements.py")],
        cwd=SOURCE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
