"""watch.py の配布・文書・手順書の規則（FR-1065 AC-364、NFR-OPS-008 AC-366）。"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class WatchDocsTest(unittest.TestCase):
    # FR-1065 AC-364
    def test_conductor_rules(self):
        t = read(".github/agents/conductor.agent.md")
        self.assertIn("watch.py stuck", t)
        self.assertIn("watch.py reap", t)
        self.assertIn("STUCK", t)
        self.assertIn("abandon", t)

    # FR-1065 AC-364
    def test_implement_fr_rules(self):
        t = read(".github/skills/implement-fr/SKILL.md")
        self.assertIn("UNRELATED-FLAKY:", t)
        self.assertIn("PARAM-045", t)

    # NFR-OPS-008 AC-366
    def test_managed_and_guide(self):
        self.assertIn('"scripts/watch.py"', read("tools/install.py"))
        g = read("users-guide/05-scripts-reference.md")
        sec = g[g.index("## watch.py"):]
        sec = sec[: sec.index("\n## ", 5)]
        for w in ("scan", "reap", "reap --under", "--item-minutes", "STUCK", "exit 2"):
            self.assertIn(w, sec)
        self.assertTrue(re.search(r"0 = .*1 = .*2 = ", sec))


if __name__ == "__main__":
    unittest.main()
