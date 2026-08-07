"""FR-TS-10: Tool Search ダッシュボード。

テキスト / JSON / 自己完結 HTML の 3 形式。データ不足の指標を 0 や推定値で埋めない。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.toolsearch.dashboard import (
    NO_DATA,
    build_dashboard,
    render_html,
    render_json,
    render_text,
)
from hve.toolsearch.stats import EVENT_CATALOG, EVENT_MISS, EVENT_QUERY, SCHEMA_VERSION, aggregate


def _query_event(**kwargs) -> dict:
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_QUERY,
        "ts": "2026-08-04T00:00:00Z",
        "run_id": "r1",
        "workflow_id": "ard",
        "step_id": "1.1",
        "query": "リソースを一覧したい",
        "limit": 5,
        "hits": ["azure_list"],
        "scores": [1.25],
        "latency_ms": 12.5,
        "catalog": {
            "total": 39,
            "pinned": 7,
            "searchable": 32,
            "dropped": 0,
            "deferred": 32,
            "mcp": 4,
            "native": 4,
            "skill": 31,
        },
        "tokens": {"baseline": 5072, "exposed": 1084},
        "warnings": [],
    }
    base.update(kwargs)
    return base


_POPULATED = (
    {
        "kind": EVENT_CATALOG,
        "ts": "2026-08-04T00:00:00Z",
        "entry_ids": ["mcp:azure:azure_list", "skill:skills:skill_unused"],
        "names": {"mcp:azure:azure_list": "azure_list", "skill:skills:skill_unused": "skill_unused"},
    },
    _query_event(),
    _query_event(query="別の語", hits=[], scores=[]),
    {"kind": EVENT_MISS, "ts": "2026-08-04T00:00:02Z", "query": "別の語"},
)


class TestRenderText(unittest.TestCase):
    def test_reports_the_headline_metrics(self) -> None:
        text = render_text(aggregate(_POPULATED))
        self.assertIn("検索回数", text)
        self.assertIn("ヒット率", text)
        self.assertIn("トークン削減", text)

    def test_lists_miss_queries(self) -> None:
        self.assertIn("別の語", render_text(aggregate(_POPULATED)))

    def test_empty_input_is_rendered_without_crashing(self) -> None:
        text = render_text(aggregate(()))
        self.assertIn(NO_DATA, text)

    def test_output_has_no_ansi_escapes_by_default(self) -> None:
        self.assertNotIn("\x1b[", render_text(aggregate(_POPULATED)))

    def test_bar_chart_width_is_bounded(self) -> None:
        """全角を 2 桁と数える。コードポイント数で揃えると日本語ラベルの桁がずれる。"""
        from hve.toolsearch.dashboard import _cols

        text = render_text(aggregate(_POPULATED), width=60)
        over = [line for line in text.splitlines() if _cols(line) > 60]
        self.assertEqual(over, [])

    def test_labels_are_padded_by_display_width(self) -> None:
        """同じブロックの ` : ` は同じ表示桁で揃う。"""
        from hve.toolsearch.dashboard import _cols

        text = render_text(aggregate(_POPULATED), width=90)
        block = [
            line
            for line in text.splitlines()
            if any(label in line for label in ("検索回数", "うち miss", "ヒット率"))
        ]
        self.assertEqual(len(block), 3)
        self.assertEqual(len({_cols(line.split(" : ")[0]) for line in block}), 1)


class TestRenderJson(unittest.TestCase):
    def test_is_valid_json(self) -> None:
        parsed = json.loads(render_json(aggregate(_POPULATED)))
        self.assertEqual(parsed["queries"], 2)

    def test_missing_metrics_stay_null(self) -> None:
        parsed = json.loads(render_json(aggregate(())))
        self.assertIsNone(parsed["hit_rate"])
        self.assertIsNone(parsed["latency_p50_ms"])


class TestRenderHtml(unittest.TestCase):
    def test_is_a_complete_document(self) -> None:
        html = render_html(aggregate(_POPULATED))
        self.assertTrue(html.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", html)

    def test_shows_no_data_instead_of_zero(self) -> None:
        self.assertIn(NO_DATA, render_html(aggregate(())))

    def test_escapes_query_text(self) -> None:
        events = (_query_event(query="<script>alert(1)</script>"),)
        html = render_html(aggregate(events))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestHtmlIsSelfContained(unittest.TestCase):
    """FR-TS-10: 外部ネットワークへ接続しない。"""

    def test_has_no_remote_references(self) -> None:
        html = render_html(aggregate(_POPULATED))
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("//cdn", html)

    def test_has_no_script_tags(self) -> None:
        self.assertNotIn("<script", render_html(aggregate(_POPULATED)).lower())

    def test_charts_are_inline_markup(self) -> None:
        self.assertIn("<svg", render_html(aggregate(_POPULATED)))


class TestNoFabrication(unittest.TestCase):
    def test_hit_rate_is_absent_rather_than_zero(self) -> None:
        self.assertIn(NO_DATA, render_text(aggregate(())))
        self.assertNotIn("0.0%", render_text(aggregate(())))

    def test_never_hit_tools_absent_without_catalog_events(self) -> None:
        text = render_text(aggregate((_query_event(),)))
        self.assertIn(NO_DATA, text)


class TestBuildDashboard(unittest.TestCase):
    def test_reads_both_stores(self) -> None:
        with TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            usage = Path(tmp) / "usage.jsonl"
            events.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in _POPULATED) + "\n",
                encoding="utf-8",
            )
            usage.write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "workflow_id": "ard",
                        "step_id": "1.1",
                        "tool_id": "mcp:azure:azure_list",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            snapshot = build_dashboard(events_path=events, usage_path=usage)
        self.assertEqual(snapshot.queries, 2)
        self.assertAlmostEqual(snapshot.adoption_rate or 0.0, 1.0)

    def test_missing_stores_are_tolerated(self) -> None:
        with TemporaryDirectory() as tmp:
            snapshot = build_dashboard(
                events_path=Path(tmp) / "none.jsonl",
                usage_path=Path(tmp) / "none2.jsonl",
            )
        self.assertEqual(snapshot.queries, 0)


class TestCli(unittest.TestCase):
    def _run(self, argv: list[str]) -> int:
        from hve.__main__ import main

        return main(argv)

    def test_text_output(self) -> None:
        with TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            events.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in _POPULATED) + "\n",
                encoding="utf-8",
            )
            code = self._run(["toolsearch", "dashboard", "--events", str(events), "--once"])
        self.assertEqual(code, 0)

    def test_html_export_writes_a_file(self) -> None:
        with TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            events.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in _POPULATED) + "\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "dash.html"
            code = self._run(
                ["toolsearch", "dashboard", "--events", str(events), "--once", "--html", str(out)]
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertIn("<!DOCTYPE html>", out.read_text(encoding="utf-8"))

    def test_json_output(self) -> None:
        with TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            events.write_text(json.dumps(_query_event(), ensure_ascii=False) + "\n", encoding="utf-8")
            code = self._run(["toolsearch", "dashboard", "--events", str(events), "--once", "--json"])
        self.assertEqual(code, 0)

    def test_parser_exposes_the_follow_interval(self) -> None:
        from hve.__main__ import _build_parser

        args = _build_parser().parse_args(["toolsearch", "dashboard", "--follow", "--interval", "5"])
        self.assertTrue(args.follow)
        self.assertEqual(args.interval, 5.0)

    def test_follow_and_once_are_mutually_exclusive(self) -> None:
        from hve.__main__ import _build_parser

        with self.assertRaises(SystemExit):
            _build_parser().parse_args(["toolsearch", "dashboard", "--follow", "--once"])


class TestDocumentation(unittest.TestCase):
    """users-guide にダッシュボードの説明があること。"""

    GUIDE = Path(__file__).resolve().parents[2] / "users-guide" / "tool-search-dashboard.md"

    def test_guide_exists(self) -> None:
        self.assertTrue(self.GUIDE.exists())

    def test_guide_documents_every_metric_key(self) -> None:
        text = self.GUIDE.read_text(encoding="utf-8")
        for key in aggregate(_POPULATED).to_dict():
            self.assertIn(key, text, f"users-guide に {key} の説明がない")

    def test_guide_documents_the_collection_paths(self) -> None:
        text = self.GUIDE.read_text(encoding="utf-8")
        self.assertIn("HVE_TOOLSEARCH_EVENTS", text)
        self.assertIn("HVE_TOOLSEARCH_USAGE", text)

    def test_guide_has_mermaid_diagrams(self) -> None:
        text = self.GUIDE.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(re.findall(r"```mermaid", text)), 2)


if __name__ == "__main__":
    unittest.main()
