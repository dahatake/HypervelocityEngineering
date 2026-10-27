"""FR-011 (AC-431 / AC-432): helpers that read Studio's web sources for the i18n tests (no browser).

- js_literals(): every string / template literal of a JS file, with its line number (comments and regex literals are skipped).
- DICT: the dictionary of web/js/i18n.js, read by importing the module in node (ja / en).
"""
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
JS_FILES = sorted((WEB / "js").glob("*.js"))
JP = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
DATA_MARK = "i18n-data"  # 管理データの値（キー・突き合わせ用の原文）を扱う行の印。同じ行、または直前のコメントだけの行に書く。
_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")


def _scan(src):
    """Return (literals, comments_by_line). literals: [(line, text)]"""
    lits, comments = [], {}
    i, n, line = 0, len(src), 1
    stack = []  # 'tpl' entries: brace depth inside ${ }
    depth = 0
    prev = ""  # previous significant char in code

    def add_comment(l, text):
        comments[l] = comments.get(l, "") + text

    def read_tpl(i, line):
        """Read template text from i until '`' (end) or '${' (nested code). Return (i, line, ended)."""
        buf, start = [], line
        while i < n:
            c = src[i]
            if c == "\\":
                buf.append(src[i:i + 2]); i += 2; continue
            if c == "`":
                lits.append((start, "".join(buf))); return i + 1, line, True
            if c == "$" and src[i + 1:i + 2] == "{":
                lits.append((start, "".join(buf))); return i + 2, line, False
            if c == "\n":
                line += 1
            buf.append(c); i += 1
        return i, line, True

    while i < n:
        c = src[i]
        if c == "\n":
            line += 1; i += 1; continue
        if c in " \t\r":
            i += 1; continue
        if src.startswith("//", i):
            j = src.find("\n", i); j = n if j < 0 else j
            add_comment(line, src[i:j]); i = j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2); j = n if j < 0 else j + 2
            for k, part in enumerate(src[i:j].split("\n")):
                add_comment(line + k, part)
            line += src[i:j].count("\n"); i = j; continue
        if c in "'\"":
            j, buf = i + 1, []
            while j < n and src[j] != c and src[j] != "\n":
                if src[j] == "\\":
                    buf.append(src[j:j + 2]); j += 2; continue
                buf.append(src[j]); j += 1
            lits.append((line, "".join(buf))); i = j + 1; prev = "a"; continue
        if c == "`":
            i, line, ended = read_tpl(i + 1, line)
            if not ended:
                stack.append(depth); depth = 0; prev = "{"
            else:
                prev = "a"
            continue
        if c == "/" and (prev == "" or prev in _REGEX_PREV):
            j, incls = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\": j += 2; continue
                if src[j] == "[": incls = True
                elif src[j] == "]": incls = False
                elif src[j] == "/" and not incls: break
                j += 1
            i = j + 1; prev = "a"; continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0 and stack:
                depth = stack.pop()
                i, line, ended = read_tpl(i + 1, line)
                if not ended:
                    stack.append(depth); depth = 0
                prev = "a"; continue
            depth -= 1
        prev = c if not (c.isalnum() or c in "_$)]") else "a"
        if c in ")]":
            prev = "a"
        i += 1
    return lits, comments


def js_literals(path):
    src = Path(path).read_text(encoding="utf-8")
    lits, comments = _scan(src)
    marked = {l for l, c in comments.items() if DATA_MARK in c}
    begin = None   # i18n-data-begin … i18n-data-end: a block of managed-data keys
    for l in sorted(comments):
        if "i18n-data-begin" in comments[l]:
            begin = l
        elif "i18n-data-end" in comments[l] and begin is not None:
            marked |= set(range(begin, l + 1)); begin = None
    marked |= {l + 1 for l in list(marked) if l not in {x for x, _ in lits}}  # 直前がコメントだけの行
    return [(l, t) for l, t in lits if l not in marked]


def hardcoded_js(path):
    """Literals with Japanese text that are not marked as managed data."""
    return [(l, t) for l, t in js_literals(path) if JP.search(t)]


class _Html(HTMLParser):
    ATTR = {"title": "data-i18n-title", "aria-label": "data-i18n-aria", "placeholder": "data-i18n-ph", "alt": "data-i18n-alt"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found, self.keys = [], [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k, v in attrs:
            if k.startswith("data-i18n") and v:
                self.keys.append(v)
        if tag not in ("meta", "link", "br", "img", "input", "path", "circle", "rect", "stop"):
            self.stack.append((tag, a))
        brand = "brand" in (a.get("class") or "").split() or "data-lang" in a
        if not brand and not any("brand" in (s[1].get("class") or "").split() for s in self.stack[:-1]):
            for k, need in self.ATTR.items():
                if k in a and a[k].strip() and need not in a:
                    self.found.append((self.getpos()[0], f"{tag} {k}={a[k]!r}"))

    def handle_endtag(self, tag):
        for j in range(len(self.stack) - 1, -1, -1):
            if self.stack[j][0] == tag:
                del self.stack[j:]; break

    def handle_data(self, data):
        if not data.strip() or not self.stack:
            return
        tag, a = self.stack[-1]
        if tag in ("script", "style", "title"):
            return
        if any("brand" in (s[1].get("class") or "").split() or "data-lang" in s[1] for s in self.stack):
            return
        if any("data-i18n" in s[1] for s in self.stack):
            return
        if re.search(r"[A-Za-z]", data) or JP.search(data):
            self.found.append((self.getpos()[0], f"{tag} text {data.strip()!r}"))


def html_scan(path=None):
    p = _Html()
    p.feed(Path(path or WEB / "index.html").read_text(encoding="utf-8"))
    return p


def load_dict():
    node = shutil.which("node")
    assert node, "node が必要です（辞書 web/js/i18n.js を読み込むため）"
    url = (WEB / "js" / "i18n.js").resolve().as_uri()
    code = (
        "globalThis.localStorage={getItem:()=>null,setItem(){}};"
        "globalThis.document={documentElement:{},querySelectorAll:()=>[]};"
        f"const m=await import({json.dumps(url)});"
        "process.stdout.write(JSON.stringify(m.DICT));"
    )
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout)


_KEY = re.compile(r"""(?<![\w.$])t\(\s*(['"`])((?:\\.|(?!\1).)*?)\1""")


def used_keys():
    """(keys, prefixes): dictionary keys referenced by t('…') in js, and by data-i18n* in index.html.
    A key that continues dynamically ('sz.level.' + x, `cam3d.${id}.n`) is returned as a prefix."""
    keys, prefixes = {}, {}
    for f in JS_FILES:
        if f.name == "i18n.js":
            continue
        src = f.read_text(encoding="utf-8")
        for m in _KEY.finditer(src):
            k, rest = m.group(2), src[m.end():m.end() + 1]
            line = src.count("\n", 0, m.start()) + 1
            if m.group(1) == "`" and "${" in k:
                prefixes[k.split("${")[0]] = (f.name, line)
            elif rest.strip() == "+" or src[m.end():m.end() + 6].lstrip().startswith("+"):
                prefixes[k] = (f.name, line)
            else:
                keys[k] = (f.name, line)
    for k in html_scan().keys:
        keys[k] = ("index.html", 0)
    return keys, prefixes
