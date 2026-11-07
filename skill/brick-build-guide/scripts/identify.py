"""Name each piece: Brickognize if you opted in, otherwise a local guess for Claude to check.

    python identify.py --work WORK

BRICKOGNIZE IS AN OUTSIDE SERVICE AND IS OFF BY DEFAULT. Turn it on with
"brickognize": {"enabled": true} in WORK/config.json, after reading its terms
(https://brickognize.com): it may keep the pictures you send, including to train its
models. This file is the only code in the kit that uses the network. When on:

* only crops of single pieces are sent, never a whole photo: the pieces on your table
  (table/crops/), the parts-list drawings from your PDF (so each element gets a part
  number) and the step drawings the picture match was unsure of;
* every crop is capped at max_side_px on its longest side;
* each crop is sent once: answers are cached by the file's MD5 in brickognize/cache.json;
* one plain-text line per send goes to brickognize/sent.log;
* if it refuses, errors or asks for payment, sending stops and the rest falls back to
  the local guess (the Claude check then covers them).

When off, each piece gets a guess from colour alone against the parts-list drawings,
scored 0, so every piece goes to the Claude check. That is slower but needs nothing
outside your computer and your Claude subscription.

Writes WORK/table/identify.json.
"""
import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


class Stop(Exception):
    pass


class Brickognize:
    def __init__(self, work, cfg):
        self.cfg = cfg
        self.dir = os.path.join(work, "brickognize")
        os.makedirs(self.dir, exist_ok=True)
        self.cache_f = os.path.join(self.dir, "cache.json")
        self.cache = C.jread(self.cache_f, {})
        self.log = open(os.path.join(self.dir, "sent.log"), "a")
        self.work = work
        self.sent = 0
        self.stopped = None

    def save(self):
        C.jwrite(self.cache_f, self.cache)

    def ask(self, path, what):
        """Top answers for one crop as [[part id, name, score], ...], or None."""
        h = C.md5(path)
        if h in self.cache:
            return self.cache[h]
        if self.stopped:
            return None
        im = cv2.imread(path)
        if im is None or max(im.shape[:2]) > self.cfg["max_side_px"]:
            raise SystemExit(f"refusing to send {path}: missing or over the size cap")
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"query_image\"; filename=\"{os.path.basename(path)}\"\r\n"
                f"Content-Type: {mimetypes.guess_type(path)[0] or 'image/jpeg'}\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.cfg["endpoint"], data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                              "User-Agent": "brick-build-guide-kit", "Accept": "application/json"})
        err, items = None, None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.cfg["timeout_s"]) as r:
                    data = json.loads(r.read().decode("utf-8"))
                items = [[it["id"], it.get("name", ""), round(float(it.get("score", 0)), 3)] for it in data.get("items", [])[:3]]
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                if e.code in (401, 402, 403, 429):
                    break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
                err = type(e).__name__
            time.sleep(3 * (attempt + 1))
        if items is None:
            self.stopped = f"{err} on {os.path.relpath(path, self.work)}"
            self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} STOPPED {self.stopped}\n")
            self.log.flush()
            return None
        self.cache[h] = items
        self.sent += 1
        top = f"{items[0][0]} {items[0][1]} ({items[0][2]})" if items else "no answer"
        self.log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} sent {os.path.relpath(path, self.work)} {im.shape[1]}x{im.shape[0]} "
                       f"md5={h} ({what}) -> {top}\n")
        self.log.flush()
        if self.sent % 25 == 0:
            self.save()
            print(f"  {self.sent} sent", flush=True)
        time.sleep(self.cfg["pause_s"])
        return items


def check_drawings(work, cfg, book, part_answers, bk):
    """Ask Brickognize about the step drawings the picture match was unsure of.

    Its part number (with the nearest colour among elements of that part) either confirms
    the picture match or disagrees with it; a disagreement goes to the Claude check."""
    by_part = {}
    for el, r in part_answers.items():
        for cand in (r or [])[:3]:
            if cand[2] >= 0.5:
                by_part.setdefault(cand[0].rstrip("abcdefghijklmnopqrstuvwxyz"), set()).add(el)
    pcol = {el: C.lab(C.piece_colour(cv2.imread(os.path.join(work, p["img"])))) for el, p in book["parts"].items()}
    out = {}
    d = os.path.join(work, "brickognize", "drawings")
    os.makedirs(d, exist_ok=True)
    close = [it for it in book["items"] if it["gap"] < cfg["review"]["drawing_gap"]]
    print(f"asking about {len(close)} step drawings the picture match was unsure of")
    for it in close:
        im = cv2.imread(os.path.join(work, it["crop"]))
        bgc = tuple(int(v) for v in C.border_colour(im))
        im = cv2.copyMakeBorder(im, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=bgc)
        k = min(3.0, cfg["brickognize"]["max_side_px"] / max(im.shape[:2]))
        f = os.path.join(d, f"{it['id']}.png")
        cv2.imwrite(f, cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC))
        r = bk.ask(f, f"step drawing {it['id']}")
        cands = set()
        for cand in (r or [])[:3]:
            cands |= by_part.get(cand[0].rstrip("abcdefghijklmnopqrstuvwxyz"), set())
        if not cands:
            continue
        col = C.lab(C.piece_colour(cv2.imread(os.path.join(work, it["crop"]))))
        pick = min(cands, key=lambda e: np.linalg.norm(col - pcol[e]))
        out[it["id"]] = dict(element=pick, agrees=pick == it["element"], bk=r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="brick-guide-work")
    a = ap.parse_args()
    work = C.work_dir(a.work)
    cfg = C.config(work)
    book = C.jread(os.path.join(work, "book", "book.json"))
    pj = C.jread(os.path.join(work, "table", "pieces.json"))
    if not book or not pj:
        C.die("run book.py and pieces.py first")
    parts = book["parts"]
    pcol = {el: C.lab(C.piece_colour(cv2.imread(os.path.join(work, p["img"])))) for el, p in parts.items()}

    bk = None
    if cfg["brickognize"]["enabled"]:
        print("Brickognize is ON: sending crops of single pieces to api.brickognize.com (an outside service "
              "that may keep them). Each is logged in brickognize/sent.log.")
        bk = Brickognize(work, cfg["brickognize"])
    else:
        print("Brickognize is off: local colour guesses only; every piece goes to the Claude check.")

    # answers from the previous photo, for pieces that are still where they were
    prev = C.jread(os.path.join(work, "table", "previous", "matched.json"), {}).get("pieces", [])
    prev = [q for q in prev if q["status"] in ("matched", "checked", "notinset") and not q.get("covered_by")]

    def still_there(p):
        for q in prev:
            if (np.hypot(q["at"][0] - p["at"][0], q["at"][1] - p["at"][1]) < 0.6 * q["r"] + 15
                    and "area" in q and 0.6 < p["area"] / max(1.0, q["area"]) < 1.6):
                return q
        return None

    out = dict(mode="brickognize" if bk else "local", parts={}, pieces={})
    reused = 0
    try:
        if bk and cfg["brickognize"]["send_parts_list_drawings"]:
            for el, p in parts.items():
                f = os.path.join(work, p["img"])
                im = cv2.imread(f)
                if max(im.shape[:2]) > cfg["brickognize"]["max_side_px"]:
                    s = cfg["brickognize"]["max_side_px"] / max(im.shape[:2])
                    f = os.path.join(work, "brickognize", f"part-{el}.png")
                    cv2.imwrite(f, cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
                out["parts"][el] = bk.ask(f, f"parts list {el}")
        if bk and cfg["brickognize"]["send_parts_list_drawings"]:
            out["drawings"] = check_drawings(work, cfg, book, out["parts"], bk)
        for p in pj["pieces"]:
            f = os.path.join(work, p["crop"])
            col = C.lab(C.piece_colour(cv2.imread(f)))
            near = sorted(parts, key=lambda el: np.linalg.norm(col - pcol[el]))[:3]
            r = dict(colour=C.colour_name(C.piece_colour(cv2.imread(f))), guess=near)
            q = still_there(p)
            if q:
                r["reused"] = dict(element=q.get("element"), status=q["status"], score=q.get("score"), bk=q.get("bk"))
                reused += 1
            elif bk and not p["big"]:
                r["bk"] = bk.ask(f, f"piece {p['id']}")
            out["pieces"][str(p["id"])] = r
        # pieces Claude pointed at by position (review.json "add" with no element): crop and name them too
        rv = C.jread(os.path.join(work, "review", "review.json"), {})
        flat = cv2.imread(os.path.join(work, "table", "flat.jpg"))
        out["added"] = {}
        for add in rv.get("add", []):
            if add.get("element"):
                continue
            x, y = (int(round(v)) for v in add["at"])
            r = int(add.get("r", 40) * 1.2) + 6
            crop = flat[max(0, y - r):y + r, max(0, x - r):x + r]
            cap = cfg["brickognize"]["max_side_px"]
            if max(crop.shape[:2]) > cap:
                crop = cv2.resize(crop, None, fx=cap / max(crop.shape[:2]), fy=cap / max(crop.shape[:2]), interpolation=cv2.INTER_AREA)
            f = os.path.join(work, "table", "crops", f"add-{x}-{y}.jpg")
            cv2.imwrite(f, crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            col = C.lab(C.piece_colour(crop))
            r_ = dict(crop=os.path.relpath(f, work), colour=C.colour_name(C.piece_colour(crop)),
                      guess=sorted(parts, key=lambda el: np.linalg.norm(col - pcol[el]))[:3])
            if bk:
                r_["bk"] = bk.ask(f, f"added piece at {x},{y}")
            out["added"][f"{x},{y}"] = r_
    finally:
        if bk:
            bk.save()
    if bk and bk.stopped:
        out["stopped"] = bk.stopped
        print(f"Brickognize stopped ({bk.stopped}); the rest fall back to the Claude check.")
    C.jwrite(os.path.join(work, "table", "identify.json"), out)
    print(f"done: {len(out['pieces'])} pieces" + (f", {reused} reused from the last photo" if reused else "")
          + (f", {bk.sent} new crops sent" if bk else ""))
    print("next: match.py")


if __name__ == "__main__":
    main()
