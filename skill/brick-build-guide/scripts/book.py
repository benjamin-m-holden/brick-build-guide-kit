"""Read your instruction PDF: the parts list, and which parts each step uses.

    python book.py --work WORK --pdf instructions.pdf

Needs poppler's pdftoppm and pdftotext. It works from the PDF's own text layer:

* The parts list is the pages where each count label ("4x") has an element ID under it.
  Each part's drawing is the picture above its count.
* A step's parts box is found from its count labels: the flat-coloured box around them.
  Each label belongs to the drawing just above it.
* Big numbers are step numbers. Main steps only ever count up, so a smaller number
  inside a sub-assembly is not mistaken for one.
* Each step drawing is matched to a parts-list drawing by picture (shape, outline,
  colour, size). Close calls go to the Claude check (review/ sheets).

Writes WORK/book/book.json, the part drawings in WORK/book/parts/, and sheets for
Claude to look at: page thumbnails (to read bag numbers), the parts list (to name
parts when Brickognize is off) and the close calls.
"""
import argparse
import collections
import glob
import os
import re
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

DPI = 100
S = DPI / 72.0
COUNT = re.compile(r"^(\d{1,3})x$")
ELEMENT = re.compile(r"^[A-Z]?\d{4,8}$")
NUMBER = re.compile(r"^\d{1,4}$")
WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        C.die(f"{cmd[0]} failed: {r.stderr.strip()[:300]}")


def render_pages(pdf, out, dpi, first=None, last=None):
    os.makedirs(out, exist_ok=True)
    cmd = ["pdftoppm", "-r", str(dpi), "-png"]
    if first:
        cmd += ["-f", str(first), "-l", str(last or first)]
    run(cmd + [pdf, os.path.join(out, "p")])
    for f in glob.glob(os.path.join(out, "p-*.png")):       # p-7.png / p-007.png -> p-007.png
        n = int(re.search(r"-(\d+)\.png$", f).group(1))
        want = os.path.join(out, f"p-{n:03d}.png")
        if f != want:
            os.replace(f, want)


def read_words(pdf, out):
    run(["pdftotext", "-bbox", pdf, out])
    pages = re.split(r"<page ", open(out, encoding="utf-8", errors="replace").read())[1:]
    W = []
    for P in pages:
        W.append([dict(x0=float(a), y0=float(b), x1=float(c), y1=float(d), t=t.strip())
                  for a, b, c, d, t in WORD.findall(P)])
    size = re.search(r'width="([\d.]+)" height="([\d.]+)"', pages[0]) if pages else None
    return W, ([float(size.group(1)), float(size.group(2))] if size else [0, 0])


def inventory_pairs(words):
    """(count word, element word) pairs: an element ID just under a count, same left edge."""
    counts = [w for w in words if COUNT.match(w["t"])]
    ids = [w for w in words if ELEMENT.match(w["t"])]
    pairs = []
    for c in counts:
        h = c["y1"] - c["y0"]
        below = [i for i in ids if abs(i["x0"] - c["x0"]) < 3 and 0 < i["y0"] - c["y0"] < 2.5 * h]
        if below:
            pairs.append((c, min(below, key=lambda i: i["y0"])))
    return pairs, counts


def trim(im, tol=30, min_area=12):
    """Crop an image to its foreground (pixels unlike the border colour)."""
    m = C.foreground(im, tol).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= min_area]
    if not keep:
        return None
    big = max(st[i, cv2.CC_STAT_AREA] for i in keep)
    keep = [i for i in keep if st[i, cv2.CC_STAT_AREA] >= 0.04 * big]
    x0 = min(st[i, 0] for i in keep); y0 = min(st[i, 1] for i in keep)
    x1 = max(st[i, 0] + st[i, 2] for i in keep); y1 = max(st[i, 1] + st[i, 3] for i in keep)
    return x0, y0, x1, y1


def features(im):
    """Picture features of one part drawing: grey pattern, outline, colour, shape, size."""
    m = C.foreground(im, 30)
    ys, xs = np.nonzero(m)
    if len(xs) < 15:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    c = im[y0:y1 + 1, x0:x1 + 1]
    mm = m[y0:y1 + 1, x0:x1 + 1]
    col = C.lab(c[mm].mean(axis=0))
    g = cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), (48, 48)).astype(float)
    g = (g - g.mean()) / (g.std() + 1e-6)
    return g, cv2.resize(mm.astype(float), (48, 48)), col, (x1 - x0 + 1) / (y1 - y0 + 1), float((x1 - x0 + 1) * (y1 - y0 + 1))


def picture_match(f, inv, top=3):
    """The best parts-list elements for a step drawing, best first, as [element, score]."""
    if f is None:
        return []
    g, m, col, ar, A = f
    out = []
    for el, F in inv.items():
        if F is None:
            continue
        g2, m2, col2, ar2, A2 = F
        s = ((g * g2).mean() * 0.6 + (1 - np.abs(m - m2).mean()) * 1.2 - np.linalg.norm(col - col2) / 60
             - abs(np.log(ar / ar2)) * 1.2 - abs(np.log(A / A2)) * 0.25)
        out.append([el, round(float(s), 3)])
    return sorted(out, key=lambda x: -x[1])[:top]


def letters(i):
    a = "abcdefghijklmnopqrstuvwxyz"
    return a[i] if i < 26 else a[i // 26 - 1] + a[i % 26]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="brick-guide-work")
    ap.add_argument("--pdf", required=True, help="the instruction PDF you downloaded")
    a = ap.parse_args()
    work = C.work_dir(a.work)
    cfg = C.config(work)
    pdf = os.path.abspath(a.pdf)
    if not os.path.exists(pdf):
        C.die(f"no such file: {pdf}")
    B = os.path.join(work, "book")
    os.makedirs(B, exist_ok=True)

    print("reading the text layer ...", flush=True)
    W, size = read_words(pdf, os.path.join(B, "words.html"))
    if not W or not any(W):
        C.die("the PDF has no text layer. This script needs one (scanned pages will not work).")
    print(f"rendering {len(W)} pages at {DPI} dpi ...", flush=True)
    render_pages(pdf, os.path.join(B, "pages"), DPI)
    page_img = lambda p: os.path.join(B, "pages", f"p-{p:03d}.png")

    # ---- the parts list
    inv_pages, parts = [], {}
    for pno, words in enumerate(W, 1):
        pairs, counts = inventory_pairs(words)
        if len(pairs) >= 4 and len(pairs) >= 0.6 * len(counts):
            inv_pages.append(pno)
    if not inv_pages:
        C.die("could not find the parts list (count labels with an element ID under each). "
              "This PDF may not have one.")
    hi = os.path.join(B, "parts-pages")
    for p in inv_pages:
        render_pages(pdf, hi, 200, p, p)
    os.makedirs(os.path.join(B, "parts"), exist_ok=True)
    inv_feat = {}
    for p in inv_pages:
        pairs, _ = inventory_pairs(W[p - 1])
        big = cv2.imread(os.path.join(hi, f"p-{p:03d}.png"))
        k = big.shape[1] / size[0]
        xs = sorted({round(c["x0"]) for c, _ in pairs})
        gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a > 15]
        cw = min(gaps) if gaps else 60
        for c, e in pairs:
            above = [i for _, i in pairs if abs(i["x0"] - c["x0"]) < cw / 2 and i["y1"] < c["y0"]]
            top = max([i["y1"] for i in above], default=0) + 1
            x0, x1 = max(0, c["x0"] - 0.2 * cw), c["x0"] + 0.95 * cw
            ry0, rx0 = int(top * k), int(x0 * k)
            reg = big[ry0:int(c["y0"] * k) - 1, rx0:int(x1 * k)].copy()
            if reg.size == 0:
                continue
            bgc = C.border_colour(reg)
            for w in W[p - 1]:                      # blank out any text (a page heading, say)
                a0, b0, a1, b1 = int(w["x0"] * k) - rx0 - 2, int(w["y0"] * k) - ry0 - 2, int(w["x1"] * k) - rx0 + 2, int(w["y1"] * k) - ry0 + 2
                if a1 > 0 and b1 > 0 and a0 < reg.shape[1] and b0 < reg.shape[0]:
                    reg[max(0, b0):b1, max(0, a0):a1] = bgc
            bb = trim(reg)
            if not bb:
                continue
            crop = reg[max(0, bb[1] - 4):bb[3] + 4, max(0, bb[0] - 4):bb[2] + 4]
            el = e["t"]
            f = os.path.join(B, "parts", f"{el}.png")
            cv2.imwrite(f, crop)
            n = int(COUNT.match(c["t"]).group(1))
            if el in parts:                     # listed twice: add the counts
                parts[el]["count"] += n
                continue
            parts[el] = dict(count=n, page=p, img=os.path.relpath(f, work))
            small = cv2.resize(crop, None, fx=DPI / 200, fy=DPI / 200, interpolation=cv2.INTER_AREA)
            inv_feat[el] = features(small)
    print(f"parts list: pages {inv_pages}, {len(parts)} kinds of part, {sum(p['count'] for p in parts.values())} pieces")

    # ---- step numbers: big numbers, counting up
    pn_h = []
    for words in W:
        nums = [w for w in words if NUMBER.match(w["t"])]
        if nums:
            low = max(nums, key=lambda w: w["y1"])          # the page number sits lowest
            if low["y0"] > 0.8 * size[1]:
                pn_h.append(low["y1"] - low["y0"])
    big_h = 1.5 * (float(np.median(pn_h)) if pn_h else 0.025 * size[1])
    mains, last = {}, 0
    for pno, words in enumerate(W, 1):
        nums = sorted({int(w["t"]) for w in words if NUMBER.match(w["t"]) and w["y1"] - w["y0"] >= big_h})
        m = [n for n in nums if last < n <= last + 12]
        if m:
            last = max(m)
        mains[pno] = (m, last)

    # ---- parts boxes and their labels
    items = []
    for pno, words in enumerate(W, 1):
        if pno in inv_pages:
            continue
        labels = [w for w in words if COUNT.match(w["t"])]
        if not labels:
            continue
        im = cv2.imread(page_img(pno))
        if im is None:
            continue
        H, Wd = im.shape[:2]
        grey = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        steps_here = [w for w in words if NUMBER.match(w["t"]) and w["y1"] - w["y0"] >= big_h and int(w["t"]) in mains[pno][0]]
        for L in labels:
            lx, ly = int(L["x0"] * S), int(L["y0"] * S)
            lh = max(4, int((L["y1"] - L["y0"]) * S))
            box = None
            for sx, sy in ((lx - 3, ly + lh // 2), (int(L["x1"] * S) + 3, ly + lh // 2), (lx, ly - 3)):
                if not (0 <= sx < Wd and 0 <= sy < H):
                    continue
                mask = np.zeros((H + 2, Wd + 2), np.uint8)
                cv2.floodFill(grey.copy(), mask, (sx, sy), 0, 5, 5, cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY | (255 << 8))
                ys, xs = np.nonzero(mask[1:-1, 1:-1])
                if len(xs) and (xs.max() - xs.min()) * (ys.max() - ys.min()) < 0.45 * H * Wd and len(xs) > 30 * lh:
                    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, grey[sy, sx])
                    break
            if box is None:      # no flat box: look in a window above the label
                box = (max(0, lx - 4 * lh), max(0, ly - 12 * lh), min(Wd, lx + 10 * lh), ly + lh, int(C.border_colour(im[max(0, ly - 12 * lh):ly + lh, max(0, lx - 4 * lh):lx + 10 * lh]).mean()))
            bx0, by0, bx1, by1, bgv = box
            reg = im[by0:by1, bx0:bx1]
            fg = (np.abs(cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY).astype(int) - int(bgv)) > 22).astype(np.uint8)
            for w in words:                                  # remove all text in the box
                x2, y2, x3, y3 = int(w["x0"] * S) - bx0, int(w["y0"] * S) - by0, int(w["x1"] * S) - bx0, int(w["y1"] * S) - by0
                if x3 > 0 and y3 > 0 and x2 < bx1 - bx0 and y2 < by1 - by0:
                    fg[max(0, y2 - 2):y3 + 3, max(0, x2 - 2):x3 + 3] = 0
            fg = cv2.dilate(fg, np.ones((5, 5), np.uint8))
            k, _, cst, _ = cv2.connectedComponentsWithStats(fg)
            best = None
            for i in range(1, k):
                x, y, w, h, area = cst[i]
                if area < 40:
                    continue
                d = np.hypot(x - (lx - bx0), (y + h) - (ly - by0)) + (0 if y + h <= ly - by0 + 6 else 500)
                if best is None or d < best[0]:
                    best = (d, i)
            if not best:
                continue
            x, y, w, h, _ = cst[best[1]]
            dx0, dy0 = bx0 + max(0, x - 2), by0 + max(0, y - 2)
            crop = im[dy0:by0 + y + h + 2, dx0:bx0 + x + w + 2]
            below = [s for s in steps_here if s["y0"] * S >= by1 - 10 and abs(s["x0"] * S - bx0) < 90 * S]
            if below:
                step = int(min(below, key=lambda s: s["y0"])["t"])
            elif mains[pno][0]:
                step = mains[pno][0][0]
            else:
                step = mains[pno][1] or 1
            cf = os.path.join(B, "steps", f"p{pno:03d}-{lx}-{ly}.png")
            os.makedirs(os.path.dirname(cf), exist_ok=True)
            cv2.imwrite(cf, crop)
            scores = dict(picture_match(features(crop), inv_feat, top=10 ** 6))
            items.append(dict(page=pno, step=step, count=int(COUNT.match(L["t"]).group(1)),
                              draw=[int(dx0), int(dy0), int(crop.shape[1]), int(crop.shape[0])], label_at=[lx, ly],
                              crop=os.path.relpath(cf, work), _scores=scores))

    # ---- labels: step + letter, left to right in the parts box
    per = collections.defaultdict(list)
    for it in items:
        per[(it["page"], it["step"])].append(it)
    for key, its in per.items():
        its.sort(key=lambda it: (it["label_at"][0] // 25, it["label_at"][1]))
        for i, it in enumerate(its):
            it["label"] = f"{key[1]}{letters(i)}"
            it["order"] = i
    items.sort(key=lambda it: (it["page"], it["step"], it["order"]))
    for i, it in enumerate(items):
        it["id"] = f"d{i + 1}"

    # ---- which part each drawing is: best picture match, but no part used more often
    # than the parts list says (best scores claim their part first)
    cap = {el: p["count"] for el, p in parts.items()}
    pick = {}
    for sc, i, el in sorted(((sc, i, el) for i, it in enumerate(items) for el, sc in it["_scores"].items()), reverse=True):
        if i not in pick and cap[el] >= items[i]["count"]:
            pick[i] = el
            cap[el] -= items[i]["count"]
    for i, it in enumerate(items):
        ranked = sorted(it.pop("_scores").items(), key=lambda x: -x[1])
        it["element"] = pick.get(i, ranked[0][0] if ranked else None)
        it["alts"] = [e for e, _ in ranked[:4] if e != it["element"]][:3]
        it["gap"] = round(ranked[0][1] - ranked[1][1], 3) if len(ranked) > 1 else 0.0
        if ranked and ranked[0][0] != it["element"]:
            it["gap"] = 0.0          # the counts overruled the picture: a close call by definition
        it["how"] = "picture+counts"

    used = collections.Counter()
    for it in items:
        if it["element"]:
            used[it["element"]] += it["count"]
    mismatch = {el: [used.get(el, 0), p["count"]] for el, p in parts.items() if used.get(el, 0) != p["count"]}

    old = C.jread(os.path.join(B, "book.json"), {})
    book = dict(pdf=pdf, pages=len(W), dpi=DPI, page_size_pt=size, inventory_pages=inv_pages, parts=parts,
                main_steps={str(p): v[0] for p, v in mains.items() if v[0]},
                last_step={str(p): v[1] for p, v in mains.items()},
                items=items, count_check=mismatch, bags=old.get("bags", {}), names=old.get("names", {}))
    C.jwrite(os.path.join(B, "book.json"), book)

    # ---- sheets for the Claude check
    R = os.path.join(work, "review")
    for f in glob.glob(os.path.join(R, "book-*.jpg")):
        os.remove(f)
    thumbs = [(cv2.imread(page_img(p)), f"page {p}") for p in range(1, len(W) + 1) if p not in inv_pages]
    for i in range(0, len(thumbs), 30):
        C.contact_sheet(thumbs[i:i + 30], os.path.join(R, f"book-pages-{i // 30 + 1:02d}.jpg"), cols=6, cell=260)
    plist = [(cv2.imread(os.path.join(work, p["img"])), el) for el, p in parts.items()]
    for i in range(0, len(plist), 48):
        C.contact_sheet(plist[i:i + 48], os.path.join(R, f"book-parts-{i // 48 + 1:02d}.jpg"), cols=8, cell=170, caption_h=30)
    close = [it for it in items if it["gap"] < cfg["review"]["drawing_gap"]]

    steps = sorted({it["step"] for it in items})
    print(f"steps: {len(steps)} numbered steps with parts, {len(items)} part labels")
    print(f"close calls (checked page by page: match.py --check-pages): {len(close)}")
    if mismatch:
        print(f"parts whose step counts do not add up to the parts list: {len(mismatch)} (book.json count_check)")
    print("next: read the bag numbers off review/book-pages-*.jpg into review.json; then table.py")


if __name__ == "__main__":
    main()
