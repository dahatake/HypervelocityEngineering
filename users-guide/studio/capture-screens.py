#!/usr/bin/env python3
"""Capture reproducible EABK Studio user-guide screens for the current commit."""

import argparse
import hashlib
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
GUIDE = Path(__file__).resolve().parent
ROUTES = ("dashboard", "map2d", "map3d", "diagrams", "placement", "source", "tables")
# (image id, route, extra query) for screens used by the role-based guides.
EXTRA = (
    ("structure", "structure", ""),
    ("consistency", "consistency", ""),
    ("maintenance", "maintenance", ""),
    ("runtime", "placement", "&kind=runtime"),
    ("cases", "tables", "&tab=cases"),
    ("states", "diagrams", "&kind=states"),
)
DETAIL_EXTRA = ("cases",)


# Required main elements per image (FR-1007 table). Each entry is (recorded label, check).
# A check is ("text", s) = s is visible in the page, ("sel", css) = css matches a visible element,
# ("re", pattern) = pattern matches the visible page text, ("svg", css) = css matches inside the diagram.
# The capture fails when any element is not on screen, so the manifest only records what the image shows.
DRAWER = [("選択対象", ("re", r"FR-001")), ("選択対象の詳細", ("sel", "#drawer h2"))]
PERSONA = [("ペルソナ", ("text", "Product Manager"))]
REQUIRED = {
    "dashboard": [
        ("対象リポジトリ名", ("repo", "")), *PERSONA,
        ("目的", ("text", "目的ごとの実装進捗")), ("進捗", ("text", "目的ごとの実装進捗")),
        ("要求の状態", ("text", "決定状態")), ("試験の状態", ("text", "SYSTEM TEST")),
        ("未回答", ("text", "未回答の質問")), ("BLOCKED", ("text", "BLOCKED の要求")),
    ],
    "map2d": [("ノード", ("sel", "#view canvas")), ("関係", ("re", r"FR-001 · \d+ 件を強調")), *DRAWER],
    "map3d": [("ノード", ("re", r"G-001\s*:\s*G-001")), ("関係", ("re", r"FR-001 · \d+ 件を強調")), *DRAWER,
              ("視点を変更できる表示", ("text", "側面"))],
    "diagrams": [("図式の種別", ("text", "状態遷移図")), ("ノード", ("svg", "g")), ("関係", ("svg", "path, line")),
                 ("根拠ID", ("re", r"G-00\d"))],
    "placement": [("ファイルまたはディレクトリ", ("text", "EABK-Studio")), ("配置関係", ("sel", "#view table tr")), *DRAWER[1:]],
    "source": [("管理データID", ("re", r"FR-001")), ("対応する実装ファイル", ("text", "eabk_model.py")), *DRAWER[1:]],
    "tables": [("対象種別", ("text", "受入基準")), ("検索", ("sel", "#view input")), ("絞込み", ("text", "決定状態:")),
               ("行一覧", ("sel", "#view table tbody tr")), *DRAWER[1:]],
    "structure": [("現状対理想構造", ("text", "全データ層の現状対理想構造"))],
    "consistency": [("層一貫性", ("text", "層一貫性ビューアー")), ("行一覧", ("sel", "#view table tr"))],
    "maintenance": [("整合性保守", ("text", "整合性保守")), ("変更候補", ("text", "NFR-COR-001"))],
    "runtime": [("実行環境の配置", ("text", "STUDIO サーバー")), ("ブラウザー", ("text", "ブラウザー")), ("対象リポジトリ", ("text", "対象リポジトリ"))],
    "cases": [("試験ケース", ("text", "試験ケース")), ("行一覧", ("sel", "#view table tbody tr")), *DRAWER[1:]],
    "states": [("図式の種別", ("text", "状態遷移図")), ("状態", ("svg", "g")), ("遷移", ("svg", "path, line"))],
    "header": [("EABK Studio", ("text", "EABK Studio"))],
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def verify_elements(page, image_id, repo_name):
    """Fail unless every required main element of the image is visible on the page."""
    body = page.evaluate("document.body.innerText")
    for label, (kind, arg) in REQUIRED[image_id]:
        if kind == "text":
            ok = arg in body
        elif kind == "re":
            ok = re.search(arg, body) is not None
        elif kind == "repo":
            ok = repo_name in body
        elif kind == "sel":
            ok = page.locator(arg).first.is_visible()
        else:
            ok = page.locator(f"#view svg {arg}").count() > 0
        if not ok:
            raise AssertionError(f"{image_id}: 必須主要要素「{label}」が画面にない")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if args.commit != head:
        raise SystemExit(f"--commit {args.commit} does not match HEAD {head}")

    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "EABK-Studio" / "studio.py"), "--repo", str(ROOT),
         "--port", str(port), "--no-open"],
        cwd=ROOT,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/model", timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("EABK Studio did not start")

        image_dir = GUIDE / "images"
        image_dir.mkdir(exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{port}")
            page.wait_for_load_state("networkidle")
            repo_name = page.evaluate("fetch('/api/model').then(r => r.json()).then(m => m.meta.name)")

            def shoot(image_id, route, query="", select="FR-001", full_page=False):
                page.goto(f"http://127.0.0.1:{port}/#/{route}?select={select}{query}")
                expect(page.locator("#view")).to_contain_text(f"Snapshot ready: {route}")
                if select:
                    expect(page.locator("#drawer")).to_be_visible()
                    expect(page.locator("#drawer")).to_contain_text(select)
                verify_elements(page, image_id, repo_name)
                page.screenshot(path=str(image_dir / f"{image_id}.png"), full_page=full_page)

            # The dashboard has no selected target (no detail drawer), so it is captured as a full page.
            shoot("dashboard", "dashboard", select="", full_page=True)
            for route in ROUTES[1:]:
                shoot(route, route)
            for image_id, route, query in EXTRA:
                shoot(image_id, route, query, select="FR-001" if image_id in DETAIL_EXTRA else "")
            # Header (tabs, search, persona bar) is hidden in snapshot links, so capture it from a normal link.
            page.goto(f"http://127.0.0.1:{port}/#/dashboard")
            expect(page.locator("#repoBtn")).to_contain_text("📁")
            verify_elements(page, "header", repo_name)
            page.add_style_tag(content="#modelTime{visibility:hidden}")
            page.locator("header.top").screenshot(path=str(image_dir / "header.png"))
            context.close()
            browser.close()

        rows = []
        screens = [(r, r) for r in ROUTES] + [(i, r) for i, r, _ in EXTRA] + [("header", "dashboard")]
        for image_id, route in screens:
            image = image_dir / f"{image_id}.png"
            rows.append({
                "screen_id": image_id,
                "image": f"images/{image_id}.png",
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "commit": head,
                "capture_command": f"python users-guide/studio/capture-screens.py --commit {head}",
                "required_elements": [label for label, _ in REQUIRED[image_id]],
            })
        (GUIDE / "screen-images.json").write_text(
            json.dumps({"screens": rows}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()
