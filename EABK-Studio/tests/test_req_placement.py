import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import eabk_model as m  # noqa: E402

BLOCK = [
    (1, "- 要求: テスト"),
    (2, "- 決定状態: 承認済み（依頼 2026-10-15）　出自: 依頼原文　優先度: MUST"),
    (3, "- 配置先: PC（ブラウザー）／保存: PC のフォルダ `docs/`・`work/`、ブラウザーの Local Storage＝レイアウト・表示設定／通信: 注文API（送信）、なし"),
    (4, "- 受入基準 AC-900: 何か"),
    (5, "  - 検証レベル: integration"),
]


# FR-1034 AC-206: the optional 配置先 field yields run location, stores and links per requirement.
def test_requirement_placement_is_extracted():
    r = m.parse_req_block("FR-900", "t", "x.md", 1, BLOCK)
    p = r["placement"]
    assert p["present"] and p["runAt"] == ["PC（ブラウザー）"]
    assert {"place": "ブラウザーの Local Storage", "data": "レイアウト・表示設定"} in p["stores"]
    assert p["links"][0] == {"peer": "注文API", "direction": "送信"}
    assert len(r["acs"]) == 1 and r["acs"][0]["level"] == "integration"  # the field does not leak into the AC


# FR-1034 AC-206 AC-202: no field, or "なし" items, read as empty ("なし"); nothing is guessed.
def test_requirement_without_placement_reads_as_none():
    r = m.parse_req_block("FR-901", "t", "x.md", 1, BLOCK[:2] + BLOCK[3:])
    assert r["placement"] == {"present": False, "runAt": [], "stores": [], "links": []}
    q = m.parse_req_placement("Azure のサービス／保存: なし／通信: なし（クライアント内のみ）")
    assert q["runAt"] == ["Azure のサービス"] and q["stores"] == [] and q["links"] == []
