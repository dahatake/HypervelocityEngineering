#!/usr/bin/env python3
"""Capture reproducible EABK Studio user-guide screens for the current commit."""

import argparse
import hashlib
import json
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


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
            for route in ROUTES:
                page.goto(f"http://127.0.0.1:{port}/#/{route}?select=FR-001")
                expect(page.locator("#view")).to_contain_text(f"Snapshot ready: {route}")
                page.screenshot(path=str(image_dir / f"{route}.png"), full_page=True)
            for image_id, route, query in EXTRA:
                page.goto(f"http://127.0.0.1:{port}/#/{route}?select=FR-001{query}")
                expect(page.locator("#view")).to_contain_text(f"Snapshot ready: {route}")
                page.screenshot(path=str(image_dir / f"{image_id}.png"), full_page=True)
            # Header (tabs, search, persona bar) is hidden in snapshot links, so capture it from a normal link.
            page.goto(f"http://127.0.0.1:{port}/#/dashboard")
            expect(page.locator("#repoBtn")).to_contain_text("📁")
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
                "capture_command": f"python EABK-Studio/users-guide/capture-screens.py --commit {head}",
                "required_elements": [f"Snapshot ready: {route}"] if image_id != "header" else ["EABK Studio"],
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
