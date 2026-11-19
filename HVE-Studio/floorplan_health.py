"""FR-1092: a quick, honest health check of the mapped source (not a security audit).

Every check reports what it had to look at (`checked`), so a short list is never mistaken for a clean bill of health.
Nothing is executed; secret values are never copied into the result (only the line and the kind).
"""
from __future__ import annotations

import re

SECRET_PATTERNS = [
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("a Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("a Stripe secret key", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("an OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]
ASSIGN = re.compile(r"""(?i)\b([\w-]*(?:api[_-]?key|secret|passw(?:or)?d|auth[_-]?token|access[_-]?token)[\w-]*)\s*[:=]\s*(['"])([^'"\s]{16,})\2""")
PLACEHOLDER = re.compile(r"(?i)your|example|change.?me|xxx|<|placeholder|dummy|sample|todo|\*{3}|fake|redacted|secret.?here|abcdef|1234567|\$\{|\{\{|%\(|process\.env|environ|getenv")
EXPOSED_ENV = re.compile(r"\b(?:VITE|NEXT_PUBLIC|REACT_APP|NUXT_PUBLIC|EXPO_PUBLIC|PUBLIC)_[A-Z0-9_]*(?:SECRET|PRIVATE|PASSWORD|TOKEN|API_?KEY|SERVICE_ROLE)[A-Z0-9_]*")
CORS_ANY = re.compile(r"""(?i)access-control-allow-origin["']?\s*[,:]\s*["']\*["']|allow_origins\s*=\s*\[\s*["']\*["']|origin\s*:\s*["']\*["']""")
AUTH_WORDS = re.compile(r"(?i)\bauth|login|token|session|permission|require_|guard|jwt|csrf|signature|passport|depends\(|headers\.get\(\s*[\"']x-|authorize")
MUTATING = {"POST", "PUT", "PATCH", "DELETE", "ANY"}
BIG = 1000


def _fix(title: str, body: str) -> str:
    return f"{title}\n\n{body}\n\nDo not print, echo or repeat any secret value in replies, commits or logs. Run the project's tests afterwards."


def run(files: list[dict], texts: dict[str, str], routes: list[dict], importers: dict[str, int], screens: list[dict], entry_names: set[str]) -> dict:
    issues: list[dict] = []
    scanned = [f for f in files if f["p"] in texts and not f.get("test")]
    # ---- secrets written into the code
    hit_files: dict[str, list[tuple[int, str]]] = {}
    for f in scanned:
        if re.search(r"(^|/)(fixtures?|examples?|samples?)/|\.example$|\.sample$", f["p"]):
            continue
        for i, line in enumerate(texts[f["p"]].split("\n"), 1):
            if len(line) > 600:
                continue
            for what, rx in SECRET_PATTERNS:
                if rx.search(line) and not PLACEHOLDER.search(line):
                    hit_files.setdefault(f["p"], []).append((i, what))
                    break
            else:
                m = ASSIGN.search(line)
                if m and not PLACEHOLDER.search(m.group(3)) and len(set(m.group(3))) >= 7 and not m.group(3).startswith(("http", "/", ".", "$")):
                    hit_files.setdefault(f["p"], []).append((i, f"a value assigned to “{m.group(1)}”"))
    for p, hits in sorted(hit_files.items()):
        issues.append({"id": "secret:" + p, "kind": "secret", "severity": "high", "title": {"key": "secret", "file": p.split("/")[-1]},
                       "items": ["f:" + p], "notes": {"f:" + p: "; ".join(f"line {ln}: {w}" for ln, w in hits[:3])},
                       "locations": [{"file": p, "line": ln} for ln, _ in hits[:5]],
                       "fix": _fix("Security fix: hard-coded secrets.", "These lines contain a secret written directly in the code:\n" + "\n".join(f"- {p}:{ln}: {w}" for ln, w in hits[:10])
                                   + "\n\nFor each one: move it to an environment variable (fail with a clear error when it is missing), add the variable name with an empty value to .env.example, make sure .env is in .gitignore, and tell me which service each key belongs to so I can rotate it.")})
    # ---- secret keys in settings the browser receives
    exposed: dict[str, list[tuple[int, str]]] = {}
    for f in scanned:
        for i, line in enumerate(texts[f["p"]].split("\n"), 1):
            m = EXPOSED_ENV.search(line)
            if m:
                exposed.setdefault(f["p"], []).append((i, m.group(0)))
    for p, hits in sorted(exposed.items()):
        issues.append({"id": "exposed:" + p, "kind": "exposed-env", "severity": "high", "title": {"key": "exposed", "file": p.split("/")[-1]}, "items": ["f:" + p],
                       "notes": {"f:" + p: "; ".join(f"line {ln}: {n}" for ln, n in hits[:3])}, "locations": [{"file": p, "line": ln} for ln, _ in hits[:5]],
                       "fix": _fix("Security fix: a secret in a browser-visible setting.", "Variables with these prefixes are sent to every visitor's browser:\n" + "\n".join(f"- {p}:{ln}: {n}" for ln, n in hits[:10])
                                   + "\n\nMove the secret to the server side and call the service from a server endpoint instead.")})
    # ---- servers that let any website call them
    cors = {}
    for f in scanned:
        for i, line in enumerate(texts[f["p"]].split("\n"), 1):
            if CORS_ANY.search(line):
                cors.setdefault(f["p"], []).append(i)
    if cors:
        issues.append({"id": "cors", "kind": "cors", "severity": "medium", "title": {"key": "cors", "n": len(cors)}, "items": ["f:" + p for p in cors],
                       "notes": {"f:" + p: "line " + ", ".join(map(str, ls[:3])) for p, ls in cors.items()},
                       "locations": [{"file": p, "line": ls[0]} for p, ls in cors.items()],
                       "fix": _fix("Security fix: CORS allows every website.", "These places allow any website to call the server:\n" + "\n".join(f"- {p}:{ls[0]}" for p, ls in cors.items())
                                   + "\n\nAllow only the origins that really need access.")})
    # ---- endpoints that change data with no check we can recognise
    open_eps = []
    by_file: dict[str, list[dict]] = {}
    for r in routes:
        by_file.setdefault(r["f"], []).append(r)
    mutating = [r for r in routes if r["m"] in MUTATING]
    for r in mutating:
        text = texts.get(r["f"], "")
        if text and not AUTH_WORDS.search(text):
            open_eps.append(r)
    if open_eps:
        issues.append({"id": "open-endpoints", "kind": "open-endpoint", "severity": "medium", "title": {"key": "open", "n": len(open_eps)},
                       "items": sorted({"f:" + r["f"] for r in open_eps}), "notes": {"f:" + r["f"]: f"{r['m']} {r['p']} (line {r['l']})" for r in open_eps},
                       "locations": [{"file": r["f"], "line": r["l"]} for r in open_eps[:10]],
                       "fix": _fix("Security fix: endpoints that change data with no sign-in check I can recognise.", "These endpoints change data, and their file mentions no sign-in, token, session or permission check:\n"
                                   + "\n".join(f"- {r['m']} {r['p']} ({r['f']}:{r['l']})" for r in open_eps[:20]) + "\n\nIf they should be private, add the project's sign-in check. If they are public on purpose, say so in a comment.")})
    # ---- very large files
    big = [f for f in files if f["loc"] > BIG and not f.get("test")]
    if big:
        issues.append({"id": "big-files", "kind": "big-file", "severity": "low", "title": {"key": "big", "n": len(big)}, "items": ["f:" + f["p"] for f in big],
                       "notes": {"f:" + f["p"]: f"{f['loc']} lines" for f in big}, "locations": [{"file": f["p"], "line": 1} for f in big],
                       "fix": _fix("Maintainability: very large files.", "These files are over 1,000 lines, which is hard to edit safely:\n" + "\n".join(f"- {f['p']} ({f['loc']} lines)" for f in big) + "\n\nSuggest where to split each one along responsibilities, without changing behaviour.")})
    # ---- files nothing uses
    screen_files = {s["file"] for s in screens}
    unused = [f for f in files if not f.get("test") and f["l"] in ("python", "javascript", "typescript") and importers.get(f["p"], 0) == 0
              and f["p"] not in screen_files and f["p"].split("/")[-1] not in entry_names and not f.get("entry")]
    if unused:
        issues.append({"id": "unused", "kind": "unused", "severity": "low", "title": {"key": "unused", "n": len(unused)}, "items": ["f:" + f["p"] for f in unused],
                       "notes": {}, "locations": [{"file": f["p"], "line": 1} for f in unused[:20]],
                       "fix": _fix("Cleanup: files nothing imports.", "No other file imports these files (entry points, tests, screens and scripts are left out):\n" + "\n".join(f"- {f['p']}" for f in unused[:30])
                                   + "\n\nCheck each one; delete it if it is dead, or tell me how it is started.")})
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["id"]))
    checked = {"files": len(scanned), "endpoints": len(routes), "mutating": len(mutating), "serverFiles": len(by_file),
               "looksLikeServer": any(re.search(r"createServer|http\.server|HTTPServer|Deno\.serve|express\(|FastAPI\(|Flask\(", t) for p, t in texts.items() if p in {f["p"] for f in scanned})}
    return {"summary": {s: sum(1 for i in issues if i["severity"] == s) for s in ("high", "medium", "low")}, "issues": issues, "checked": checked}
