"""FR-1081 定型文の自動付与（AC-453〜456）の結合テスト。"""
import json
import sys

from conftest import SOURCE, run

PREFIX = ".github/ebak-prompt-prefix.md"


def prompt(repo, text="こんにちは"):
    return repo.gate("user-prompt", {"sessionId": "s1", "prompt": text})


def set_cfg(repo, **kw):
    p = repo.path / "scripts" / "ebak.config.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["prompt_prefix"] = kw
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# FR-1081 AC-453: 有効で文章が空でないとき、/build template 以外に additionalContext を返す
def test_prefix_is_attached_by_default_and_follows_edits(sample):
    out = prompt(sample)
    assert "additionalContext" in out
    assert sample.read(PREFIX).strip() in out["additionalContext"]
    sample.write(PREFIX, "独自の文章です\n")  # AC-457 の一部: 書き換えが次の Prompt から効く
    assert prompt(sample)["additionalContext"].endswith("独自の文章です")


# FR-1081 AC-454: 無い・空・無効・root 外のときは何も付けない
def test_no_prefix_when_missing_empty_disabled_or_outside_root(sample):
    (sample.path / PREFIX).unlink()
    assert prompt(sample) == {}
    sample.write(PREFIX, " \n\t\n")
    assert prompt(sample) == {}
    sample.write(PREFIX, "本文")
    assert "additionalContext" in prompt(sample)
    set_cfg(sample, enabled=False, file=PREFIX)
    assert prompt(sample) == {}
    outside = sample.path.parent / "outside.md"
    outside.write_text("外", encoding="utf-8")
    set_cfg(sample, enabled=True, file="../outside.md")
    assert prompt(sample) == {}


# FR-1081 AC-455: /build template には付けない
def test_no_prefix_for_build_template(sample):
    assert prompt(sample, "/build template") == {}


# FR-1081 AC-456: インストーラは無いときだけ作り、既存を上書きしない
def test_installer_creates_prefix_only_when_missing(repo):
    installed = repo.read(PREFIX)
    for key in ("専門家", "最も生の素材", "手法とツール", "書き直したプロンプトを実行"):
        assert key in installed
    repo.write(PREFIX, "利用者の書き換え\n")
    run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(repo.path), "--skip-verify"],
        repo.path, check=True)
    assert repo.read(PREFIX) == "利用者の書き換え\n"
