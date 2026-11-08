from pathlib import Path

HERE = Path(__file__).parent


def test_ui_tests_share_one_playwright_loop():
    # sync_playwright() を conftest 以外で開くと、同一プロセスで asyncio ループが衝突して ERROR になる
    offenders = [p.name for p in HERE.glob("test_*.py")
                 if "sync_playwright(" in p.read_text(encoding="utf-8") and p.name != Path(__file__).name]
    assert offenders == [], f"shared_browser fixture を使うこと: {offenders}"
