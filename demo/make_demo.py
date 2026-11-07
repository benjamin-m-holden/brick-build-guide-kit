"""Build the Pebble Rover demo: a made-up set, run through the real pipeline.

    python demo/make_demo.py --out _site

1. Draws a made-up instruction book as a PDF with a real text layer (cover, five step
   pages, a parts list) and an overhead photo of a table with the pieces spread out
   on it, a few still missing and three strays from "another set". Everything is
   drawn by code (render.py); nothing comes from a real set or a real photo.
2. Runs the skill's scripts on them, exactly as for a real set: book.py, table.py,
   pieces.py, identify.py (Brickognize off: the demo parts are invented), match.py
   and site.py.
3. The Claude check is stood in for by demo/review.json: the answers written by
   looking at the review sheets of this demo. Pieces are keyed by position so the
   file still fits if a library update renumbers them.

Needs the skill's requirements plus reportlab, and poppler (pdftoppm, pdftotext).
"""
import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "skill", "brick-build-guide", "scripts")
sys.path.insert(0, HERE)
from model import BAGS, MISSING, PARTS, SET, STEPS, STRAYS  # noqa: E402
from render import cyl_z, frame_of, gid, make, overhead, render, rot_z  # noqa: E402

PW, PH = 560, 500                         # page size in points
PAGEBG, BOXBG, BOXLINE, INK = (236, 243, 250), (255, 255, 255), (120, 160, 205), (28, 42, 70)


def args_of(p):
    return {k: v for k, v in p.items() if k in ("w", "d", "h", "r")}


def polys(el, x=0, y=0, z=0):
    p = PARTS[el]
    return make(p["kind"], x, y, z, p["hex"], **args_of(p))


def rgb(c):
    return tuple(v / 255 for v in c)


def bag_icon(n):
    im = Image.new("RGBA", (160, 180), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 22, 150, 172], 18, fill=(250, 250, 250, 255), outline=INK, width=6)
    d.rectangle([10, 22, 150, 44], fill=INK)
    sys.path.insert(0, SCRIPTS)
    import common
    d.text((80, 110), str(n), fill=INK, font=common.font(80), anchor="mm")
    return im


def make_pdf(path):
    need = {}
    for _, _, items in STEPS:
        for el, *_ in items:
            need[el] = need.get(el, 0) + 1
    pim = {el: render(polys(el), scale=70, pad=12) for el in PARTS}
    allp = [q for _, _, items in STEPS for el, x, y, z in items for q in polys(el, x, y, z)]
    MS = 46
    msize, morig = frame_of(allp, scale=MS, pad=14)
    c = canvas.Canvas(path, pagesize=(PW, PH))
    c.setTitle(f"{SET['name']} (made-up demo set)")

    def page_bg(pno):
        c.setFillColorRGB(*rgb(PAGEBG))
        c.rect(0, 0, PW, PH, stroke=0, fill=1)
        c.setFillColorRGB(*rgb(INK))
        c.setFont("Helvetica", 10)
        c.drawRightString(PW - 18, 14, str(pno))

    # 1: cover
    page_bg(1)
    cover = render(allp, scale=60, pad=20)
    w = 360
    h = w * cover.size[1] / cover.size[0]
    c.drawImage(ImageReader(cover), (PW - w) / 2, 70, w, h, mask="auto")
    c.setFont("Helvetica-Bold", 30)
    c.drawString(30, PH - 60, SET["name"])
    c.setFont("Helvetica", 12)
    c.drawString(30, PH - 82, "A made-up set for the brick-build-guide-kit demo. Drawn by code.")
    c.showPage()
    # 2: before you start
    page_bg(2)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(30, PH - 60, "Before you build")
    c.setFont("Helvetica", 12)
    for i, line in enumerate(["Spread the pieces out on a light, plain table.", "Open bag one first.",
                              "Each step shows the new parts in a box at its top left."]):
        c.drawString(30, PH - 100 - 20 * i, line)
    c.showPage()

    built = []
    for pno in sorted({p for p, _, _ in STEPS}):
        page_bg(pno)
        ss = [(st, items) for p, st, items in STEPS if p == pno]
        bh = (PH - 40) / len(ss)
        if pno in BAGS:
            c.drawImage(ImageReader(bag_icon(BAGS[pno])), PW - 70, PH - 78, 48, 54, mask="auto")
        for i, (st, items) in enumerate(ss):
            top = PH - 20 - i * bh
            if i:
                c.setStrokeColorRGB(*rgb((196, 212, 230)))
                c.setLineWidth(1.5)
                c.line(20, top + 4, PW - 20, top + 4)
            for el, x, y, z in items:
                built.extend(polys(el, x, y, z))
            cnt = {}
            for el, *_ in items:
                cnt[el] = cnt.get(el, 0) + 1
            sizes = []
            for el in cnt:
                im = pim[el]
                s = min(56 / im.size[0], 40 / im.size[1])
                sizes.append((el, im, im.size[0] * s, im.size[1] * s))
            boxw = sum(max(w_, 22) + 14 for _, _, w_, _ in sizes) + 10
            boxtop, boxh = top - 8, 70
            c.setFillColorRGB(*rgb(BOXBG))
            c.setStrokeColorRGB(*rgb(BOXLINE))
            c.setLineWidth(1.5)
            c.roundRect(20, boxtop - boxh, boxw, boxh, 8, stroke=1, fill=1)
            x_ = 30
            for el, im, w_, h_ in sizes:
                c.drawImage(ImageReader(im), x_, boxtop - 8 - 40 + (40 - h_), w_, h_, mask="auto")
                c.setFillColorRGB(*rgb(INK))
                c.setFont("Helvetica-Bold", 10)
                c.drawString(x_, boxtop - boxh + 7, f"{cnt[el]}x")
                x_ += max(w_, 22) + 14
            c.setFont("Helvetica-Bold", 28)
            c.drawString(22, boxtop - boxh - 34, str(st))
            m = render(list(built), scale=MS, size=msize, origin=morig)
            ax0, ay0, ax1, ay1 = 150, top - bh + 8, PW - 20, boxtop - 4
            s = min((ax1 - ax0) / m.size[0], (ay1 - ay0) / m.size[1])
            c.drawImage(ImageReader(m), ax0 + (ax1 - ax0 - m.size[0] * s) / 2, ay0, m.size[0] * s, m.size[1] * s, mask="auto")
        c.showPage()

    # parts list
    plist = max(p for p, _, _ in STEPS) + 1
    page_bg(plist)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColorRGB(*rgb(INK))
    c.drawString(30, PH - 44, "Parts in this set")
    els = sorted(PARTS, key=lambda e: (-need[e], e))
    for i, el in enumerate(els):
        cx, cy = 34 + (i % 4) * 128, PH - 80 - (i // 4) * 120
        im = pim[el]
        s = min(70 / im.size[0], 52 / im.size[1])
        c.drawImage(ImageReader(im), cx, cy - 52 + (52 - im.size[1] * s), im.size[0] * s, im.size[1] * s, mask="auto")
        c.setFillColorRGB(*rgb(INK))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(cx, cy - 68, f"{need[el]}x")
        c.setFont("Helvetica", 8)
        c.drawString(cx, cy - 79, el)
    c.showPage()
    c.save()
    return need


def lying(p, x, y):
    if p["kind"] == "wheel":
        r = p.get("r", 1.05)
        P = cyl_z(x, y, 0, r, 1.0, p["hex"], n=28)
        ang = [2 * math.pi * i / 28 for i in range(28)]
        for rr, col in ((r * .62, "#c9ccd1"), (r * .2, "#55595e")):
            P.append(([(x + rr * math.cos(a), y + rr * math.sin(a), 1.01 + (.01 if col == "#55595e" else 0)) for a in ang], col, gid()))
        return P
    w = p.get("w", 2 if p["kind"] == "slope" else 1)
    d = p.get("d", 1)
    return make(p["kind"], x - w / 2, y - d / 2, 0, p["hex"], **args_of(p))


def footprint(p):
    return (2.1, 2.1) if p["kind"] == "wheel" else (p.get("w", 2 if p["kind"] == "slope" else 1), p.get("d", 1))


def make_photo(path, need):
    random.seed(7)
    TS, TW, TH = 46, 42, 27                     # px per stud; table size in studs
    loose = [dict(el=el, **PARTS[el]) for el in PARTS for _ in range(need[el] - MISSING.get(el, 0))]
    loose += [dict(el=None, **s) for s in STRAYS]
    loose.sort(key=lambda p: -math.hypot(*footprint(p)))
    placed, scene = [], []
    for p in loose:
        w, d = footprint(p)
        rad = math.hypot(w, d) / 2 + .35
        best = None
        for _ in range(3000):
            x, y = random.uniform(2 + rad, TW - 2 - rad), random.uniform(2 + rad, TH - 2 - rad)
            gap = min([math.hypot(x - q["x"], y - q["y"]) - rad - q["rad"] for q in placed] or [9])
            if best is None or gap > best[0]:
                best = (gap, x, y)
            if gap > 1.4:
                break
        _, x, y = best
        P = rot_z(lying(p, x, y), random.uniform(0, math.pi), x, y)
        placed.append(dict(p, x=x, y=y, rad=rad))
        scene += P
    tw, th = TW * TS, TH * TS
    light = np.array([-.25, -.45, 1]) / np.linalg.norm([-.25, -.45, 1])
    lay = render(scene, proj=overhead, scale=TS, size=(tw, th), origin=(0, 0), light=light)
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
    noise = np.asarray(Image.fromarray((rng.random((60, 90)) * 255).astype(np.uint8)).resize((tw, th), Image.BICUBIC), np.float32) / 255 - .5
    tone = (1 - .10 * (((xx / tw - .5) * 1.6) ** 2 + ((yy / th - .5) * 1.6) ** 2)) * (1 + .03 * noise)
    table = Image.fromarray(np.clip(np.array([214, 219, 223], np.float32) * tone[..., None], 0, 255).astype(np.uint8)).convert("RGBA")
    al = lay.split()[3]
    shadow = Image.new("RGBA", lay.size, (40, 40, 50, 0))
    shadow.putalpha(al.point(lambda v: int(v * .45)))
    shadow = shadow.transform(lay.size, Image.AFFINE, (1, 0, -7, 0, 1, -10)).filter(ImageFilter.GaussianBlur(7))
    table.alpha_composite(shadow)
    table.alpha_composite(lay)
    table = cv2.cvtColor(np.asarray(table.convert("RGB")), cv2.COLOR_RGB2BGR)
    # the room: a darker floor, the table seen a little off square
    PWpx, PHpx = 2400, 1700
    floor = (rng.normal(0, 9, (PHpx, PWpx, 3)) + np.array([78, 92, 108])).clip(0, 255).astype(np.uint8)
    floor = cv2.GaussianBlur(floor, (3, 3), 0)
    dst = np.float32([[250, 200], [2170, 250], [2235, 1525], [185, 1470]])
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [tw, 0], [tw, th], [0, th]]), dst)
    warped = cv2.warpPerspective(table, H, (PWpx, PHpx))
    mask = cv2.warpPerspective(np.full((th, tw), 255, np.uint8), H, (PWpx, PHpx))
    photo = np.where(mask[..., None] > 127, warped, floor)
    cv2.imwrite(path, photo, [cv2.IMWRITE_JPEG_QUALITY, 90])
    truth = []
    for q in placed:
        u, v = q["x"] * TS, q["y"] * TS
        truth.append(dict(element=q["el"], name=q["name"], table_px=[round(u / tw, 4), round(v / th, 4)]))
    return truth


def run(script, *a):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *a], text=True, capture_output=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f"{script} failed")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"), help="where the built demo site goes")
    ap.add_argument("--work", default=os.path.join(ROOT, "_demo-work"), help="work folder for the pipeline")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    shutil.rmtree(work, ignore_errors=True)
    inp = os.path.join(work, "input")
    os.makedirs(inp)
    need = make_pdf(os.path.join(inp, "pebble-rover.pdf"))
    truth = make_photo(os.path.join(inp, "table.jpg"), need)
    with open(os.path.join(inp, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)
    with open(os.path.join(work, "config.json"), "w") as f:
        json.dump({"site": {"title": "Pebble Rover (demo)", "storage_prefix": "pebble-demo:"}}, f)
    rv = os.path.join(HERE, "review.json")
    if os.path.exists(rv):
        os.makedirs(os.path.join(work, "review"))
        shutil.copy(rv, os.path.join(work, "review", "review.json"))
    run("book.py", "--work", work, "--pdf", os.path.join(inp, "pebble-rover.pdf"))
    run("table.py", "--work", work, "--photo", os.path.join(inp, "table.jpg"))
    run("pieces.py", "--work", work)
    run("identify.py", "--work", work)
    run("match.py", "--work", work, "--check-pages", "3-7")
    note = ("<p><b>This is a demo.</b> The Pebble Rover, its instruction book and the table photo are made up and drawn by code. "
            "The guide itself was built by the kit's own scripts from that PDF and photo, with Brickognize off; "
            "the Claude check's answers are in demo/review.json.</p>"
            "<p class=\"tryit\">Try it: tap <b>Next</b> to build, tick parts as you find them, and tap a part's name to see where it is on the table.</p>")
    run("site.py", "--work", work, "--all", "--demo-note", note)
    shutil.rmtree(a.out, ignore_errors=True)
    shutil.copytree(os.path.join(work, "site"), a.out)
    os.remove(os.path.join(a.out, "state.json"))
    print(f"demo site: {os.path.join(a.out, 'index.html')}")


if __name__ == "__main__":
    main()
