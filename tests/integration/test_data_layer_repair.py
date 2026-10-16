"""データ層の確認・修復のコマンド（rdfix.py --full）の結合テストの入口
（FR-1046 AC-242/243、NFR-REL-002 AC-244/245/246/247、NFR-REL-003 AC-248/249/250）。

本体は tests/toolkit/test_rdfix_full.py（導入先を模した使い捨てのリポジトリで、rdfix・verify・install を実際に実行し、
故障はテストの側から注入する）。tests/toolkit は要求 ID の走査の対象外なので、要求 ID と受入基準 ID をこのファイルに書いて、
要求からテストをたどれるようにする。
"""
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]


# FR-1046 AC-242 AC-243 / NFR-REL-002 AC-244 AC-245 AC-246 AC-247 / NFR-REL-003 AC-248 AC-249 AC-250
def test_data_layer_repair_suite_passes():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", str(SOURCE / "tests" / "toolkit" / "test_rdfix_full.py")],
        cwd=SOURCE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
