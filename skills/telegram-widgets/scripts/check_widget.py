#!/usr/bin/env python3
"""
Check a Telegram widget before sending it: size the way the server counts it, plus a lint for
features the widget sandbox (profile 1) removes or that broke in practice.

    python3 check_widget.py widget.html [--image BYTES] [--json]

Exit code 0: fits and no errors. 1: errors (too large, NUL, forbidden features). Warnings never fail.
Standard library only; works for widgets of bots written in any language.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zlib

LIMIT_RAW = 32768
LIMIT_ZLIB = 4096
BUDGET_ZLIB = 4000

# (regex, severity, message). Severity "error": the feature is removed or breaks the widget.
RULES: list[tuple[str, str, str]] = [
    (r"<(input|select|textarea|option|fieldset|form)\b", "error", "form controls are removed; only <button> works"),
    (r"<(video|audio|iframe|object|embed|dialog|progress|meter|template)\b", "error", "element is removed by the sandbox"),
    (r"<script[^>]+\bsrc\s*=", "error", "external scripts never load (no network, no CDN)"),
    (r"<link\b|@import\b|@font-face\b", "error", "stylesheets, imports and web fonts are removed"),
    (r"<img[^>]+src\s*=\s*[\"'](?!data:image/(png|jpe?g|gif|webp))", "error", "images must be data: PNG/JPEG/GIF/WebP"),
    (r"data:image/svg", "error", "data: SVG images are out; inline the <svg> instead"),
    (r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts)\s*\(|new\s+(WebSocket|Worker|EventSource)\b",
     "error", "network APIs throw NetworkDisabledError"),
    (r"\b(alert|confirm|prompt)\s*\(", "error", "alert/confirm/prompt show nothing"),
    (r"navigator\.clipboard", "error", "use TelegramWidget.copyText instead of navigator.clipboard"),
    (r"\b(getImageData|putImageData|toDataURL|toBlob|createPattern|createConicGradient)\b", "error", "canvas method is out of the profile"),
    (r"globalCompositeOperation|shadowBlur|ctx\.filter|\.filter\s*=", "error", "canvas compositing/shadows/filters are out"),
    (r"\b(location\.(href|assign|replace)|history\.(push|replace)State)", "error", "navigation is blocked"),
    (r"\d+(\.\d+)?(vh|dvh|svh|lvh)\b", "error", "height-relative units are removed"),
    (r"color-mix\(|oklch\(|oklab\(|\blch\(|\blab\(|\bhwb\(|color\(", "error", "modern color functions are removed"),
    (r":has\(|:focus|:checked|::marker|::first-letter|::first-line|:target", "error", "selector is removed"),
    (r"overflow(-[xy])?\s*:\s*(auto|scroll)", "warn", "overflow auto/scroll becomes hidden: nothing scrolls inside a widget"),
    (r"position\s*:\s*sticky", "warn", "sticky becomes relative"),
    (r"text-shadow|line-clamp|clip-path|mix-blend-mode|backface-visibility|perspective", "error", "CSS property is removed"),
    (r"(margin|padding|inset)-(inline|block)", "error", "logical properties are removed"),
    (r"<(clipPath|mask|pattern|marker|foreignObject|animate|animateTransform|animateMotion)\b", "error", "SVG element is removed"),
    (r"font-family\s*:[^;}]*[\"']", "warn", "named fonts are removed; use system-ui, sans-serif, serif, monospace, ui-*"),
    (r"\.arc\([^)]*,\s*(7|6\.3|6\.29)\s*(,|\))", "warn", "arc end angle above 2π: use Math.PI*2 (pitfall 1)"),
    (r"\.rect\([^)]*\)\s*;?\s*\w+\.arc\(", "warn", "rect() then arc() in one path: Telegram may draw a stripe; dim, clip and redraw instead (pitfall 1)"),
    (r"\.innerHTML\s*=[^;]*(chatData|publicData|\.result|\bS\.e\b)", "warn", "state or answers rendered with innerHTML; use textContent for non-constant text"),
    (r"addEventListener\(\s*[\"']touch|ontouch", "warn", "touch events are not delivered; use pointer events"),
    (r"addEventListener\(\s*[\"'](keydown|keyup|keypress|wheel|scroll)[\"']", "warn", "keyboard, wheel and scroll events are not delivered"),
    (r"onpointerdown[^;{]*request\(|pointerdown[^}]*\.request\(", "warn", "request() from pointerdown is refused; call it from click or pointerup"),
]


def strip_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def check(html: str, image_bytes: int = 0) -> dict:
    raw = html.encode("utf-8")
    z = len(zlib.compress(raw, 9)) + int(image_bytes * 1.0)  # base64 of a compressed image ~ its own size
    findings = []
    body = strip_comments(html)
    for pattern, severity, message in RULES:
        for m in re.finditer(pattern, body, flags=re.I):
            line = body.count("\n", 0, m.start()) + 1
            findings.append({"severity": severity, "line": line, "match": m.group(0)[:60], "message": message})
    opacity = len(re.findall(r"opacity\s*:\s*0?\.\d", body)) + len(re.findall(r"filter\s*:", body))
    if opacity > 8:
        findings.append({"severity": "warn", "line": 0, "match": f"{opacity} rules",
                         "message": "many opacity/filter rules; at most 16 such elements may be visible at once"})
    if "\x00" in html:
        findings.append({"severity": "error", "line": 0, "match": "NUL", "message": "NUL character: INPUT_MEDIA_WIDGET_HTML_INVALID"})
    if "TelegramWidget" in body and "chatDataChanged" not in body and "chatData" in body:
        findings.append({"severity": "warn", "line": 0, "match": "chatData",
                         "message": "reads chatData but never listens to chatDataChanged: bot edits will not redraw"})
    if "request(" in body and "catch" not in body:
        findings.append({"severity": "warn", "line": 0, "match": "request(",
                         "message": "request() can reject (BUSY, TIMEOUT, ...) and throw synchronously: handle both"})
    size_errors = []
    if len(raw) > LIMIT_RAW:
        size_errors.append(f"raw size {len(raw)} > {LIMIT_RAW}")
    if z > LIMIT_ZLIB:
        size_errors.append(f"compressed size {z} > {LIMIT_ZLIB}")
    return {"raw_bytes": len(raw), "zlib9_bytes": z, "budget": BUDGET_ZLIB, "limit": LIMIT_ZLIB,
            "size_errors": size_errors, "findings": findings}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--image", type=int, default=0, help="bytes of an image you will inject later as data: URI")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    html = open(args.file, encoding="utf-8").read()
    r = check(html, args.image)
    errors = r["size_errors"] + [f for f in r["findings"] if f["severity"] == "error"]
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        state = "OK" if r["zlib9_bytes"] <= BUDGET_ZLIB else ("TIGHT" if r["zlib9_bytes"] <= LIMIT_ZLIB else "TOO LARGE")
        print(f"size: raw {r['raw_bytes']} B, zlib-9 {r['zlib9_bytes']} B of {LIMIT_ZLIB} (budget {BUDGET_ZLIB}): {state}")
        for e in r["size_errors"]:
            print(f"ERROR  {e}")
        for f in r["findings"]:
            where = f"line {f['line']}: " if f["line"] else ""
            print(f"{f['severity'].upper():6} {where}{f['message']}  [{f['match']}]")
        print("result:", "FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
