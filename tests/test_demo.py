"""End-to-end test: build the demo and compare what the pipeline found with what was drawn.

    python -m pytest tests/        (or: python tests/test_demo.py)

The demo generator knows where it put every piece (truth.json), so this checks the
whole pipeline on a known answer: the PDF parse, the table corners, piece finding, and
the review answers being applied.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "demo"))
from model import MISSING, STEPS, STRAYS  # noqa: E402

_built = {}


def build():
    if not _built:
        d = tempfile.mkdtemp(prefix="bbgk-test-")
        subprocess.run([sys.executable, os.path.join(ROOT, "demo", "make_demo.py"), "--out", os.path.join(d, "site"),
                        "--work", os.path.join(d, "work")], check=True, capture_output=True)
        _built["d"] = d
    return _built["d"]


def load(*p):
    with open(os.path.join(build(), *p)) as f:
        return json.load(f)


def test_book_parts_list():
    book = load("work", "book", "book.json")
    need = {}
    for _, _, items in STEPS:
        for el, *_ in items:
            need[el] = need.get(el, 0) + 1
    assert {el: p["count"] for el, p in book["parts"].items()} == need
    assert book["count_check"] == {}


def test_book_steps():
    book = load("work", "book", "book.json")
    want = sorted((pg, st, el, n) for pg, st, items in STEPS
                  for el, n in {e: sum(1 for x in items if x[0] == e) for e, *_ in items}.items())
    got = sorted((it["page"], it["step"], it["element"], it["count"]) for it in book["items"])
    assert got == want
    labels = [it["label"] for it in book["items"] if it["page"] == 6]
    assert labels == ["5a", "5b", "6a"]
    assert {int(k): v for k, v in book["bags"].items()} == {3: 1, 5: 2}


def test_table_pieces():
    truth = load("work", "input", "truth.json")
    pj = load("work", "table", "pieces.json")
    W, H = pj["flat_size"]
    pieces = pj["pieces"]
    assert len(pieces) == len(truth) == sum(1 for _ in truth)
    for t in truth:                    # every drawn piece has a detection within a stud or so
        x, y = t["table_px"][0] * W, t["table_px"][1] * H
        d = min(math.hypot(p["at"][0] - x, p["at"][1] - y) for p in pieces)
        assert d < 0.03 * W, (t, d)


def test_after_review():
    truth = load("work", "input", "truth.json")
    mt = load("work", "table", "matched.json")
    W, H = load("work", "table", "pieces.json")["flat_size"]
    right = 0
    for t in truth:
        x, y = t["table_px"][0] * W, t["table_px"][1] * H
        p = min(mt["pieces"], key=lambda p: math.hypot(p["at"][0] - x, p["at"][1] - y))
        right += (p.get("element") == t["element"] and p["status"] == "checked") or (t["element"] is None and p["status"] == "notinset")
    assert right == len(truth)
    on_table = len(truth) - len(STRAYS)
    assert sum(len(v) for v in mt["found"].values()) == on_table
    assert "D1012" not in mt["found"] and len(mt["found"]["D1003"]) == 4 - MISSING["D1003"]


def test_site_is_self_contained():
    page = open(os.path.join(build(), "site", "index.html")).read()
    assert "http://" not in page.replace("http://www.w3.org", "")
    for ext in ('src="https://', "<script src=", "<link rel=\"stylesheet\""):
        assert ext not in page
    assert page.count('class="pg"') == 2 + 5          # setup, inventory, five book pages


def test_new_photo_reuses_answers():
    """A second photo of an unchanged table: every piece keeps its answer, nothing is re-checked."""
    import shutil
    src = os.path.join(build(), "work")
    work = src + "-again"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(src, work)
    scripts = os.path.join(ROOT, "skill", "brick-build-guide", "scripts")
    for s, *a in (("table.py", "--photo", os.path.join(work, "input", "table.jpg")), ("pieces.py",), ("identify.py",), ("match.py",)):
        subprocess.run([sys.executable, os.path.join(scripts, s), "--work", work, *a], check=True, capture_output=True)
    with open(os.path.join(work, "table", "matched.json")) as f:
        mt = json.load(f)
    assert all(p.get("reused") for p in mt["pieces"])
    assert mt["queue"] == []
    assert mt["found"] == load("work", "table", "matched.json")["found"]


def test_closeups():
    """A close-up of part of the same table is used for sharper crops; an unrelated picture is not."""
    import shutil
    import cv2
    import numpy as np
    src = os.path.join(build(), "work")
    work = src + "-closeup"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(src, work)
    photo = cv2.imread(os.path.join(work, "input", "table.jpg"))
    h, w = photo.shape[:2]
    quad = np.float32([[0.24 * w, 0.22 * h], [0.70 * w, 0.20 * h], [0.72 * w, 0.76 * h], [0.23 * w, 0.78 * h]])
    out = np.float32([[0, 0], [3600, 0], [3600, 2700], [0, 2700]])
    close = cv2.warpPerspective(photo, cv2.getPerspectiveTransform(quad, out), (3600, 2700), flags=cv2.INTER_CUBIC)
    cf, junk = os.path.join(work, "close.jpg"), os.path.join(work, "junk.jpg")
    cv2.imwrite(cf, close)
    rng = np.random.default_rng(1)
    cv2.imwrite(junk, cv2.GaussianBlur((rng.random((900, 1200, 3)) * 255).astype(np.uint8), (9, 9), 0))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "skill", "brick-build-guide", "scripts", "pieces.py"),
                        "--work", work, "--closeups", cf, junk], check=True, capture_output=True, text=True)
    assert "close-up close.jpg: matched" in r.stdout and "junk.jpg: does not match" in r.stdout
    with open(os.path.join(work, "table", "pieces.json")) as f:
        pieces = json.load(f)["pieces"]
    used = [p for p in pieces if p["src"] == "close.jpg"]
    assert len(used) >= 3
    before = {p["id"]: p for p in load("work", "table", "pieces.json")["pieces"]}
    for p in used:
        a = cv2.imread(os.path.join(work, p["crop"]))
        b = cv2.imread(os.path.join(src, before[p["id"]]["crop"]))
        assert a.shape[0] > b.shape[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
