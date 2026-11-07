"""Find the tabletop in your overhead photo and flatten it.

    python table.py --work WORK --photo table.jpg            # find the corners automatically
    python table.py --work WORK --corners '[[x,y],...]'      # use corners from the crop fixer

The surface colour is taken from the middle of the photo (the most common colour
there), every pixel of that colour is marked, and the biggest such area is the table.
A straight line is fitted along each of its four edges and the corners are where the
lines meet, so a rounded corner or a piece over the edge does not pull a corner in.

Writes WORK/table/corners.json, table/check.jpg (the photo with the outline drawn),
table/flat.jpg (the table seen square-on) and fixcrop/index.html: a page where you
drag the four corners by hand if the outline is wrong. Open it in a browser, press
Done, and give the corners it prints back to this script with --corners.
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def find_corners(photo):
    h, w = photo.shape[:2]
    s = 1000 / max(h, w)
    sm = cv2.resize(photo, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(cv2.GaussianBlur(sm, (7, 7), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    H, W = lab.shape[:2]
    mid = lab[int(H * .3):int(H * .7), int(W * .3):int(W * .7)].reshape(-1, 3)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, lbl, centres = cv2.kmeans(mid, 4, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    lbl = lbl.ravel()
    main = np.bincount(lbl, minlength=4).argmax()
    # colour matters more than brightness: a wood table has light and dark planks, and
    # shadow, but the same hue. Every big cluster of the main hue counts as surface.
    wgt = np.float32([0.5, 1, 1])
    surf = [c for i, c in enumerate(centres) if np.linalg.norm((c - centres[main])[1:]) < 12 and (lbl == i).mean() > 0.1]
    spread = np.median(np.linalg.norm(((mid[lbl == main] - centres[main]) * wgt), axis=1))
    d = np.min([np.linalg.norm((lab - c) * wgt, axis=2) for c in surf], axis=0)
    m = (d < max(14, 2.5 * spread)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))     # cut thin bridges to the floor
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))   # pieces on the table are holes: close them
    n, cc, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None, "no surface found"
    big = cc[H // 2, W // 2] or 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
    if st[big, cv2.CC_STAT_AREA] < 0.15 * H * W:
        return None, "the surface found is too small"
    region = (cc == big).astype(np.uint8) * 255
    cnt = max(cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    if cv2.contourArea(hull) > 0.96 * H * W:
        return np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]), "the table fills the photo"
    ext = None
    for eps in np.linspace(0.01, 0.1, 19):
        a = cv2.approxPolyDP(hull, eps * cv2.arcLength(hull, True), True)
        if len(a) == 4:
            ext = a.reshape(4, 2).astype(np.float32)
            break
    if ext is None:
        return None, "the surface is not four-sided"
    c = ext.mean(0)
    ext = ext[np.argsort(np.arctan2(ext[:, 1] - c[1], ext[:, 0] - c[0]))]
    ext = np.roll(ext, -np.argmin(ext.sum(1)), 0)            # top-left first, then clockwise
    P = hull.reshape(-1, 2).astype(np.float32)
    # densify the hull so each edge has points to fit
    dense = []
    for i in range(len(P)):
        a_, b_ = P[i], P[(i + 1) % len(P)]
        k = max(2, int(np.linalg.norm(b_ - a_) / 3))
        dense += [a_ + (b_ - a_) * t for t in np.linspace(0, 1, k, endpoint=False)]
    P = np.float32(dense)
    lines = []
    for i in range(4):
        a_, b_ = ext[i], ext[(i + 1) % 4]
        v = b_ - a_
        L = np.linalg.norm(v)
        u = v / L
        nrm = np.array([-u[1], u[0]])
        t = (P - a_) @ u
        dd = np.abs((P - a_) @ nrm)
        sel = P[(t > 0.2 * L) & (t < 0.8 * L) & (dd < 0.05 * L)]
        if len(sel) < 5:
            sel = np.float32([a_, b_])
        lines.append(cv2.fitLine(sel, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel())

    def meet(l1, l2):
        (vx1, vy1, x1, y1), (vx2, vy2, x2, y2) = l1, l2
        t = np.linalg.solve(np.array([[vx1, -vx2], [vy1, -vy2]]), np.array([x2 - x1, y2 - y1]))
        return np.array([x1 + vx1 * t[0], y1 + vy1 * t[0]])
    try:
        q = np.float32([meet(lines[3], lines[0]), meet(lines[0], lines[1]), meet(lines[1], lines[2]), meet(lines[2], lines[3])]) / s
    except np.linalg.LinAlgError:
        q = ext / s
    return q, "found automatically"


def flat_size(q, long_side):
    wpx = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    hpx = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    k = long_side / max(wpx, hpx)
    return int(round(wpx * k)), int(round(hpx * k))


def write_fixer(work, photo_path, q, size):
    d = os.path.join(work, "fixcrop")
    os.makedirs(d, exist_ok=True)
    im = C.to_pil(C.load_photo(photo_path))
    im.thumbnail((2000, 2000))
    im.save(os.path.join(d, "photo.jpg"), quality=85)
    t = open(os.path.join(C.SKILL, "site", "fixcrop.html")).read()
    t = t.replace("__W0__", str(size[0])).replace("__H0__", str(size[1])).replace("__AUTO__", json.dumps(np.round(q).astype(int).tolist()))
    open(os.path.join(d, "index.html"), "w").write(t)
    return os.path.join(d, "index.html")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="brick-guide-work")
    ap.add_argument("--photo", help="overhead photo of the whole table")
    ap.add_argument("--corners", help='corners from the crop fixer: [[x,y],[x,y],[x,y],[x,y]] or its whole JSON line')
    a = ap.parse_args()
    work = C.work_dir(a.work)
    cfg = C.config(work)
    T = os.path.join(work, "table")
    os.makedirs(T, exist_ok=True)
    keep = os.path.join(T, "photo" + os.path.splitext(a.photo or ".jpg")[1].lower())
    if a.photo:
        if not os.path.exists(a.photo):
            C.die(f"no such file: {a.photo}")
        if os.path.exists(os.path.join(T, "matched.json")):       # a new photo: keep the last answers to reuse
            prev = os.path.join(T, "previous")
            os.makedirs(prev, exist_ok=True)
            for f in ("matched.json", "pieces.json"):
                shutil.copy(os.path.join(T, f), os.path.join(prev, f))
            for f in ("matched.json", "identify.json"):
                if os.path.exists(os.path.join(T, f)):
                    os.remove(os.path.join(T, f))
            rf = os.path.join(work, "review", "review.json")
            rv = C.jread(rf, {})
            if rv.get("pieces") or rv.get("add"):           # piece numbers belong to the old photo
                rv.setdefault("earlier_photos", []).append({"pieces": rv.pop("pieces", {}), "add": rv.pop("add", [])})
                C.jwrite(rf, rv)
            print("new photo: answers from the last photo are kept and reused for pieces that have not moved")
        for f in os.listdir(T):
            if f.startswith("photo."):
                os.remove(os.path.join(T, f))
        shutil.copy(a.photo, keep)
    old = C.jread(os.path.join(T, "corners.json"), {})
    photo_path = os.path.join(work, old["photo"]) if old.get("photo") and not a.photo else keep
    if not os.path.exists(photo_path):
        C.die("give the table photo with --photo")
    photo = C.load_photo(photo_path)
    h, w = photo.shape[:2]

    if a.corners:
        v = json.loads(a.corners)
        q = np.float32(v["corners"] if isinstance(v, dict) else v)
        how = "set by hand"
    else:
        q, how = find_corners(photo)
        if q is None:
            q = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
            how = f"not found ({how}); using the whole photo. Fix it with fixcrop/index.html"
    FW, FH = flat_size(q, cfg["table"]["flat_long_side_px"])
    M = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [FW, 0], [FW, FH], [0, FH]]))
    flat = cv2.warpPerspective(photo, M, (FW, FH))
    cv2.imwrite(os.path.join(T, "flat.jpg"), flat, [cv2.IMWRITE_JPEG_QUALITY, 92])
    chk = photo.copy()
    cv2.polylines(chk, [np.int32(q)], True, (0, 230, 255), max(3, w // 300))
    for i, p in enumerate(q):
        cv2.circle(chk, tuple(int(v) for v in p), max(8, w // 150), (255, 0, 255), -1)
    cv2.imwrite(os.path.join(T, "check.jpg"), cv2.resize(chk, None, fx=1600 / max(h, w), fy=1600 / max(h, w)), [cv2.IMWRITE_JPEG_QUALITY, 85])
    C.jwrite(os.path.join(T, "corners.json"), dict(photo=os.path.relpath(photo_path, work), size=[w, h], corners=q.round(1).tolist(),
                                                  how=how, flat_size=[FW, FH], H=M.tolist()))
    fx = write_fixer(work, photo_path, q, (w, h))
    print(f"table corners {how}: {np.round(q).astype(int).tolist()}")
    print(f"flattened table: table/flat.jpg ({FW} x {FH})")
    print(f"look at table/check.jpg; if the outline is off, open {fx} and drag the corners")


if __name__ == "__main__":
    main()
