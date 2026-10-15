"""Static wiring of repo-switch failure recovery (NFR-OPS-003 AC-028)."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web" / "js"


def js(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


# NFR-OPS-003 AC-028: every failure branch offers Retry / Back and never clears the model
def test_switch_failure_branches_offer_retry_and_back_and_keep_model():
    app = js("app.js")
    body = app.split("async function switchRepository", 1)[1].split("window.addEventListener('hashchange'", 1)[0]
    failure, success = body.split("    return;\n", 1)
    assert "repo.retry" in failure and "repo.back" in failure
    assert "t('repo.nodata')" in failure and "t('repo.bad')" in failure
    assert "store.clear" not in failure
    assert "store.clear" in success


# NFR-OPS-003 AC-028: labels exist in both languages
def test_recovery_labels_defined_in_ja_and_en():
    ja, en = js("i18n.js").split("  en: {", 1)
    for key in ("repo.retry", "repo.back"):
        assert f"'{key}'" in ja and f"'{key}'" in en
