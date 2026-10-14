"""Build the static documentation site from the main repository's Markdown.

Usage: python build.py <path-to-repo-checkout>   (output goes next to this script)
Requires: pip install markdown
"""
import html
import posixpath
import re
import shutil
import sys
from pathlib import Path

import markdown

SRC = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent
GH = "https://github.com/dahatake/HypervelocityEngineering"
SITE = "HypervelocityEngineering"

GROUPS = [
    ("はじめに", ["README.md", "CHANGELOG.md"]),
    ("ユーザーガイド", sorted(p.relative_to(SRC).as_posix() for p in (SRC / "users-guide").glob("*.md"))),
    ("Studio ガイド", sorted(p.relative_to(SRC).as_posix() for p in (SRC / "users-guide/studio").glob("*.md"))),
    ("管理データ（docs）", sorted(p.relative_to(SRC).as_posix() for p in (SRC / "docs").glob("*.md"))),
]
PAGES = {}  # repo path -> out path
for _, files in GROUPS:
    for f in files:
        if not (SRC / f).exists():
            continue
        if f == "README.md":
            PAGES[f] = "index.html"
        elif f == "users-guide/README.md":
            PAGES[f] = "users-guide/index.html"
        else:
            PAGES[f] = re.sub(r"\.md$", ".html", f).lower() if f.startswith("docs/") else re.sub(r"\.md$", ".html", f)

THEMES = [
    ("light", "Light"), ("dark", "Dark"), ("midnight", "Midnight"),
    ("ocean", "Ocean"), ("forest", "Forest"), ("sunset", "Sunset"), ("rose", "Rose"),
]

CSS = """
:root{--bg:#fff;--fg:#1f2328;--muted:#656d76;--card:#f6f8fa;--bd:#d0d7de;--ac:#0969da;--side:#f6f8fa;--code:#eff1f3;--r:10px}
[data-theme=dark]{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--card:#161b22;--bd:#30363d;--ac:#58a6ff;--side:#010409;--code:#1c2128}
[data-theme=midnight]{--bg:#0f1226;--fg:#e4e7ff;--muted:#9aa0cc;--card:#171a3a;--bd:#2c3062;--ac:#8b9cff;--side:#0a0c1d;--code:#1d2147}
[data-theme=ocean]{--bg:#f2fafc;--fg:#0c2d3a;--muted:#4f7583;--card:#e0f2f7;--bd:#b4dce6;--ac:#0087a8;--side:#dcf0f5;--code:#d3ebf1}
[data-theme=forest]{--bg:#f4f8f2;--fg:#1c2b1e;--muted:#5a6f5c;--card:#e6efe2;--bd:#c3d6bd;--ac:#2f7d3a;--side:#e1ecdc;--code:#dae7d5}
[data-theme=sunset]{--bg:#fff8f2;--fg:#3a2118;--muted:#8a6252;--card:#ffebdc;--bd:#f2cdb3;--ac:#d9480f;--side:#ffeede;--code:#fde1cc}
[data-theme=rose]{--bg:#fff6f8;--fg:#3a1c26;--muted:#8d5a6b;--card:#ffe6ec;--bd:#f2c2cf;--ac:#c2255c;--side:#ffe9ef;--code:#fcdbe4}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 system-ui,"Segoe UI","Hiragino Sans","Yu Gothic UI",sans-serif;transition:background .2s,color .2s}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:1rem;padding:.6rem 1.2rem;background:var(--card);border-bottom:1px solid var(--bd);backdrop-filter:blur(6px)}
header .brand{font-weight:700;color:var(--fg)}header .sp{flex:1}
header select,header button{background:var(--bg);color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:.3rem .6rem;font:inherit;font-size:.9rem}
#menu{display:none}
.layout{display:flex;min-height:calc(100vh - 54px)}
nav{width:290px;flex:none;background:var(--side);border-right:1px solid var(--bd);padding:1rem;position:sticky;top:54px;height:calc(100vh - 54px);overflow:auto;font-size:.9rem}
nav h4{margin:1.1rem 0 .3rem;color:var(--muted);font-size:.75rem;letter-spacing:.06em;text-transform:uppercase}
nav a{display:block;padding:.25rem .6rem;border-radius:6px;color:var(--fg);line-height:1.4}
nav a:hover{background:var(--card);text-decoration:none}
nav a.cur{background:var(--ac);color:#fff}
main{flex:1;min-width:0;max-width:900px;margin:0 auto;padding:2rem 1.5rem 4rem}
h1,h2{border-bottom:1px solid var(--bd);padding-bottom:.3rem}
h1,h2,h3,h4{line-height:1.3;scroll-margin-top:70px}
img{max-width:100%;height:auto;border-radius:var(--r);border:1px solid var(--bd)}
pre{background:var(--code);border:1px solid var(--bd);border-radius:var(--r);padding:1rem;overflow:auto;line-height:1.5;font-size:.88rem}
code{background:var(--code);padding:.15em .4em;border-radius:5px;font:.88em ui-monospace,Consolas,monospace}
pre code{background:none;padding:0}
pre.mermaid{background:var(--card);text-align:center}
table{border-collapse:collapse;display:block;overflow:auto;margin:1rem 0}
th,td{border:1px solid var(--bd);padding:.45rem .8rem;vertical-align:top}
th{background:var(--card)}tr:nth-child(even) td{background:color-mix(in srgb,var(--card) 50%,transparent)}
blockquote{margin:1rem 0;padding:.2rem 1rem;border-left:4px solid var(--ac);background:var(--card);border-radius:0 var(--r) var(--r) 0;color:var(--muted)}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--bd);color:var(--muted);font-size:.85rem}
@media(max-width:820px){#menu{display:inline-block}nav{position:fixed;left:-310px;top:54px;z-index:9;transition:left .2s}nav.open{left:0}main{padding:1.2rem 1rem}}
"""

JS = """
const t=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
const sel=document.getElementById('theme');
function setT(v){document.documentElement.dataset.theme=v;localStorage.setItem('theme',v);sel.value=v;
 const hl=document.getElementById('hl');if(hl)hl.href='https://cdn.jsdelivr.net/npm/highlight.js@11/styles/github'+(['dark','midnight'].includes(v)?'-dark':'')+'.min.css';}
sel.onchange=()=>setT(sel.value);setT(t);
document.getElementById('menu').onclick=()=>document.querySelector('nav').classList.toggle('open');
document.querySelector('nav a.cur')?.scrollIntoView({block:'center'});
"""


def rel(from_out, to_out):
    return posixpath.relpath(to_out, posixpath.dirname(from_out) or ".")


def fix_links(body, src_path, out_path, assets):
    base = posixpath.dirname(src_path)

    def sub(m):
        attr, url = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:|#|data:)", url):
            return m.group(0)
        path, _, frag = url.partition("#")
        target = posixpath.normpath(posixpath.join(base, path)) if path else src_path
        frag = "#" + frag if frag else ""
        if target in PAGES:
            return f'{attr}="{rel(out_path, PAGES[target])}{frag}"'
        f = SRC / target
        if f.is_file() and attr == "src":
            assets.add(target)
            return f'{attr}="{rel(out_path, target)}"'
        if f.is_dir():
            return f'{attr}="{GH}/tree/main/{target}{frag}"'
        if f.is_file():
            return f'{attr}="{GH}/blob/main/{target}{frag}"'
        return m.group(0)

    return re.sub(r'(href|src)="([^"]*)"', sub, body)


def nav_html(out_path, cur):
    parts = []
    for title, files in GROUPS:
        items = [f for f in files if f in PAGES]
        if not items:
            continue
        parts.append(f"<h4>{title}</h4>")
        for f in items:
            text = first_heading(f) or f
            c = ' class="cur"' if f == cur else ""
            parts.append(f'<a{c} href="{rel(out_path, PAGES[f])}">{html.escape(text)}</a>')
    return "\n".join(parts)


_titles = {}


def first_heading(f):
    if f not in _titles:
        m = re.search(r"^#\s+(.+)$", (SRC / f).read_text(encoding="utf-8"), re.M)
        _titles[f] = re.sub(r"[`*_]", "", m.group(1)).strip() if m else None
    return _titles[f]


def main():
    assets = set()
    for f in PAGES:
        md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                               extension_configs={"toc": {"permalink": False}})
        body = md.convert((SRC / f).read_text(encoding="utf-8"))
        body = body.replace('<pre><code class="language-mermaid">', '<pre class="mermaid"><code>')
        body = re.sub(r'(<pre class="mermaid"><code>)(.*?)(</code></pre>)',
                      lambda m: '<pre class="mermaid">' + m.group(2) + "</pre>", body, flags=re.S)
        out_path = PAGES[f]
        body = fix_links(body, f, out_path, assets)
        title = first_heading(f) or SITE
        opts = "".join(f'<option value="{k}">{v}</option>' for k, v in THEMES)
        root = rel(out_path, "index.html")
        page = f"""<!DOCTYPE html>
<html lang="ja" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — {SITE}</title>
<link id="hl" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11/styles/github.min.css">
<style>{CSS}</style>
<script>document.documentElement.dataset.theme=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light')</script>
</head><body>
<header><button id="menu" aria-label="menu">☰</button><a class="brand" href="{root}">⚡ {SITE}</a><span class="sp"></span>
<label>🎨 <select id="theme" aria-label="theme">{opts}</select></label>
<a href="{GH}">GitHub</a></header>
<div class="layout"><nav>{nav_html(out_path, f)}</nav>
<main>{body}<footer>出典: <a href="{GH}/blob/main/{f}">{f}</a></footer></main></div>
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11/lib/common.min.js"></script>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
const dark=['dark','midnight'].includes(document.documentElement.dataset.theme);
mermaid.initialize({{startOnLoad:false,theme:dark?'dark':'default'}});
await mermaid.run({{querySelector:'pre.mermaid'}});
</script>
<script>document.querySelectorAll('pre code').forEach(e=>hljs.highlightElement(e));{JS}</script>
</body></html>"""
        dest = OUT / out_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page, encoding="utf-8")
    for a in assets:
        dest = OUT / a
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC / a, dest)
    (OUT / ".nojekyll").write_text("")
    print(f"{len(PAGES)} pages, {len(assets)} assets")


main()
