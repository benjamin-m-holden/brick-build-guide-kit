"""Match the pieces to your parts list, sort out what Claude should check, apply its answers.

    python match.py --work WORK                    # match, apply review.json, write sheets
    python match.py --work WORK --check-pages 6-9  # also: sheets of close-call drawings on pages 6-9

Each piece gets a status:

  matched     Brickognize was sure (score >= min_score, no near tie) and named a part in
              your parts list. Where a part comes in several colours, the nearest colour wins.
  low         needs the Claude check: score below min_score, a near tie, Brickognize's top
              answer is not in your parts list but a lower one is, or Brickognize is off.
  notinset    none of Brickognize's answers is in your parts list (a stray from another set).
  noanswer    Brickognize returned nothing.
  big         too big or lumpy for the scripts; Claude picks these out by eye.
  checked     Claude's answer, from review/review.json.

review/review.json holds every answer from the Claude check. All keys are optional:

  "bags":     {"3": 1, "5": 2}            page a numbered bag starts on -> bag number
  "names":    {"D1002": "Yellow brick 1 x 2"}   plain names for parts (shown in the guide)
  "parts":    {"D1002": "3004"}             element -> part number, if Brickognize is off
  "drawings": {"d17": "D1006"}             step drawing id (sheets) -> element
  "pieces":   {"12": "D1002", "40": "not-in-set", "41": "not-a-piece",
               "@1520,880": {"element": "D1002", "count": 2}}
                   piece number on the sheets (or "@x,y" on table/grid.jpg) -> answer;
                   count is for a blob that is really several touching pieces
  "add":      [{"at": [1200, 340], "r": 60, "element": "D1001"}, {"at": [900, 410], "r": 20}]
                   a piece the scripts missed or could not separate (positions from
                   table/grid.jpg); smaller blobs inside its circle are dropped. Leave
                   out "element" and identify.py crops the spot and names it like any
                   other piece (rerun identify.py, then match.py). Answers in "pieces"
                   can refer to added pieces by their number on the sheets.
"""
import argparse
import collections
import glob
import os
import re
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

RING = {"matched": (60, 200, 60), "checked": (60, 200, 60), "low": (0, 190, 255), "notinset": (40, 40, 230),
        "noanswer": (40, 40, 230), "big": (230, 60, 230), "ignored": (150, 150, 150)}


def base(pid):
    return re.sub(r"[a-z]+$", "", str(pid or ""))


def page_range(s):
    a, _, b = s.partition("-")
    return range(int(a), int(b or a) + 1)


def strip(images, h=150, divider_after=0):
    images = [im for im in images if im is not None]
    images = [cv2.resize(im, (max(1, int(im.shape[1] * h / im.shape[0])), h)) for im in images]
    out = np.full((h + 10, sum(im.shape[1] + 12 for im in images) + 12, 3), 255, np.uint8)
    x = 6
    for j, im in enumerate(images):
        out[5:5 + h, x:x + im.shape[1]] = im
        x += im.shape[1] + 12
        if j == divider_after:
            cv2.line(out, (x - 6, 0), (x - 6, h + 10), (0, 0, 255), 2)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="brick-guide-work")
    ap.add_argument("--check-pages", help="write close-call drawing sheets for these book pages, e.g. 6-9")
    a = ap.parse_args()
    work = C.work_dir(a.work)
    cfg = C.config(work)
    rv = cfg["review"]
    book = C.jread(os.path.join(work, "book", "book.json"))
    pj = C.jread(os.path.join(work, "table", "pieces.json"))
    ident = C.jread(os.path.join(work, "table", "identify.json"))
    if not (book and pj and ident):
        C.die("run book.py, table.py, pieces.py and identify.py first")
    R = os.path.join(work, "review")
    review = C.jread(os.path.join(R, "review.json"), {})
    parts = book["parts"]
    img = lambda el: cv2.imread(os.path.join(work, parts[el]["img"])) if el in parts else None

    # Claude's answers that belong to the book
    for it in book["items"]:
        bd = (ident.get("drawings") or {}).get(it["id"])
        if bd:
            it["how"] = "confirmed" if bd["agrees"] else "disagree"
            it["bk_element"] = bd["element"]
        if it["id"] in review.get("drawings", {}):
            it["element"] = review["drawings"][it["id"]]
            it["how"] = "checked"
    book["bags"] = {str(k): v for k, v in review.get("bags", book.get("bags", {})).items()}
    names = {}
    for el, r in (ident.get("parts") or {}).items():
        if r:
            names[el] = r[0][1]
    names.update(review.get("names", {}))
    book["names"] = names
    C.jwrite(os.path.join(work, "book", "book.json"), book)

    # element <-> part number
    by_part = collections.defaultdict(set)
    part_of = {}
    for el, r in (ident.get("parts") or {}).items():
        for cand in (r or [])[:3]:
            if cand[2] >= 0.5:
                by_part[base(cand[0])].add(el)
        if r:
            part_of[el] = base(r[0][0])
    for el, pid in review.get("parts", {}).items():
        by_part[base(pid)].add(el)
        part_of[el] = base(pid)
    pcol = {el: C.lab(C.piece_colour(img(el))) for el in parts}

    flat = cv2.imread(os.path.join(work, "table", "flat.jpg"))
    def classify(p, r):
        """Status, element and score for one piece from its identify.py result."""
        bk = r.get("bk")
        p["bk"] = bk
        if r.get("reused"):
            u = r["reused"]
            p.update(element=u["element"], status=u["status"], score=u.get("score"), bk=u.get("bk"), reused=True)
        elif p["big"]:
            p["status"] = "big"
        elif ident["mode"] == "local" or "bk" not in r:
            p["status"] = "low"
            p["element"] = p["guess"][0] if p["guess"] else None
            p["score"] = 0.0
        elif not bk:
            p["status"] = "noanswer"
        else:
            els, sc, alt = [], 0.0, False
            for k, cand in enumerate(bk[:3]):
                if by_part.get(base(cand[0])):
                    els, sc, alt = sorted(by_part[base(cand[0])]), cand[2], k > 0
                    p["partno"] = base(cand[0])
                    break
            if not els:
                p["status"] = "notinset"
            else:
                col = C.lab(C.piece_colour(cv2.imread(os.path.join(work, p["crop"]))))
                els.sort(key=lambda e: np.linalg.norm(col - pcol[e]))
                p["element"], p["score"], p["colour_alts"] = els[0], sc, els[1:3]
                tie = len(bk) > 1 and bk[0][2] - bk[1][2] < rv["tie_margin"] and base(bk[0][0]) != base(bk[1][0])
                p["status"] = "matched" if sc >= rv["min_score"] and not tie and not alt else "low"

    pieces = []
    for p in pj["pieces"]:
        p = dict(p)
        r = ident["pieces"].get(str(p["id"]), {})
        p["guess"] = r.get("guess", [])
        p["colour"] = r.get("colour")
        classify(p, r)
        pieces.append(p)

    # apply the Claude check
    def nearest(x, y):
        best = min(pieces, key=lambda q: np.hypot(q["at"][0] - x, q["at"][1] - y), default=None)
        return best if best and np.hypot(best["at"][0] - x, best["at"][1] - y) < max(40, best["r"]) else None
    answered = {k for k in review.get("pieces", {}) if not k.startswith("@")}
    nid = max([q["id"] for q in pieces] + [999]) + 1
    for add in review.get("add", []):
        x, y = add["at"]
        r = float(add.get("r", 40))
        for q in pieces:
            if str(q["id"]) not in answered and q["status"] != "ignored" and np.hypot(q["at"][0] - x, q["at"][1] - y) < r:
                q["status"] = "ignored"
                q["covered_by"] = nid
        c = flat[max(0, int(y - r)):int(y + r), max(0, int(x - r)):int(x + r)]
        cf = os.path.join(work, "table", "crops", f"{nid:03d}.jpg")
        cv2.imwrite(cf, c)
        el = add.get("element")
        q = dict(id=nid, at=[x, y], r=r, big=False, crop=os.path.relpath(cf, work), by="claude", count=add.get("count", 1))
        if el:
            q.update(element=el, status="checked" if el in parts else "notinset")
        else:                               # pointed at by position: named by identify.py, like any piece
            ar = (ident.get("added") or {}).get(f"{int(round(x))},{int(round(y))}")
            if ar:
                q.update(crop=ar["crop"], guess=ar.get("guess", []), colour=ar.get("colour"))
                classify(q, ar)
            else:
                q.update(status="low", element=None, note="run identify.py to name it")
        pieces.append(q)
        nid += 1

    reviewed = set()
    for key, ans in review.get("pieces", {}).items():
        if key.startswith("@"):
            x, y = (float(v) for v in key[1:].split(","))
            p = nearest(x, y)
        else:
            p = next((q for q in pieces if str(q["id"]) == key), None)
        if not p:
            print(f"review.json: no piece for {key}")
            continue
        reviewed.add(p["id"])
        el = ans["element"] if isinstance(ans, dict) else ans
        p["count"] = ans.get("count", 1) if isinstance(ans, dict) else 1
        if el == "not-in-set":
            p["status"] = "notinset"
        elif el == "not-a-piece":
            p["status"] = "ignored"
        elif el in parts:
            p.update(element=el, status="checked", by="claude")
        else:
            print(f"review.json: {key}: {el} is not in the parts list")
    found = collections.defaultdict(list)
    for p in pieces:
        if p.get("element") in parts and p["status"] in ("matched", "checked", "low"):
            found[p["element"]] += [p["id"]] * p.get("count", 1)
    stats = collections.Counter(p["status"] for p in pieces)
    queue = [p for p in pieces if p["status"] in ("low", "noanswer", "big") and p["id"] not in reviewed]
    C.jwrite(os.path.join(work, "table", "matched.json"), dict(mode=ident["mode"], stopped=ident.get("stopped"),
             settings=rv, stats=dict(stats), pieces=pieces, found=found, queue=[p["id"] for p in queue]))

    # pictures: the setup map, and sheets for whatever still needs the Claude check
    mp = flat.copy()
    for p in pieces:
        if p["status"] == "ignored":
            continue
        cv2.circle(mp, (int(p["at"][0]), int(p["at"][1])), int(p["r"] + 8), RING[p["status"]], 6)
    cv2.imwrite(os.path.join(work, "table", "setup-map.jpg"), mp, [cv2.IMWRITE_JPEG_QUALITY, 85])
    for f in glob.glob(os.path.join(R, "table-*.jpg")):
        os.remove(f)
    tiles = []
    for p in queue:
        crop = cv2.imread(os.path.join(work, p["crop"]))
        cands = ([p["element"]] if p.get("element") else []) + [e for e in p.get("guess", []) if e != p.get("element")]
        bk = f" bk {p['bk'][0][0]} {p['bk'][0][2]:.2f}" if p.get("bk") else ""
        tiles.append((strip([crop] + [img(e) for e in cands[:3]]), f"#{p['id']} {p['status']}{bk}: " + " / ".join(cands[:3])))
    for i in range(0, len(tiles), 12):
        C.contact_sheet(tiles[i:i + 12], os.path.join(R, f"table-{i // 12 + 1:02d}.jpg"), cols=2, cell=620, cell_h=170, caption_h=30)
    if a.check_pages:
        pr = page_range(a.check_pages)
        close = [it for it in book["items"] if it["page"] in pr and it.get("how") not in ("checked", "confirmed")
                 and (it["gap"] < rv["drawing_gap"] or it.get("how") == "disagree")]
        dt = []
        for it in close:
            cands = list(dict.fromkeys(e for e in [it["element"], it.get("bk_element")] + it["alts"] if e))[:4]
            note = f" (Brickognize: {it['bk_element']})" if it.get("how") == "disagree" else ""
            dt.append((strip([cv2.imread(os.path.join(work, it["crop"]))] + [img(e) for e in cands]),
                       f"{it['id']} p{it['page']} {it['label']}: " + " / ".join(cands) + note))
        for f in glob.glob(os.path.join(R, "drawings-*.jpg")):
            os.remove(f)
        for i in range(0, len(dt), 12):
            C.contact_sheet(dt[i:i + 12], os.path.join(R, f"drawings-{a.check_pages}-{i // 12 + 1:02d}.jpg"), cols=2, cell=620, cell_h=170, caption_h=30)
        print(f"pages {a.check_pages}: {len(close)} step drawings to check (review/drawings-*.jpg)")

    print(f"mode {ident['mode']}: " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    print(f"kinds of part seen on the table: {len(found)} of {len(parts)}")
    print(f"for the Claude check: {len(queue)} pieces (review/table-*.jpg); then one look at table/setup-map.jpg for misses")


if __name__ == "__main__":
    main()
