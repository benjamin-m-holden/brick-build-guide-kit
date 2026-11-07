"""Find every piece on the flattened table.

    python pieces.py --work WORK

Works on table/flat.jpg (from table.py). A pixel is part of a piece when it differs
from the local table colour (a heavily blurred copy of the table), or sits on a strong
edge. Where the table is bright (glare), smaller differences count. Pieces that touch
are split where they narrow (watershed). A blob that is neither small nor a clean,
solid shape is flagged "big": scripts are unreliable on touching big plates in glare,
so Claude picks those out by eye on table/grid.jpg.

Close-ups (optional, --closeups a.jpg b.jpg): photos of parts of the table taken from
closer, at the same time as the overhead photo. Each is matched to the overhead photo
(SIFT features and a homography). Pieces are still found on the overhead photo, but a
piece a close-up covers gets its crop cut from the close-up, so small pieces are sent
or checked at a higher resolution. Close-ups that do not match are reported and skipped.

Writes table/pieces.json, a crop of each piece (table/crops/NNN.jpg, never bigger than
the Brickognize size cap), table/pieces-map.jpg with each piece numbered, and
table/grid.jpg with a coordinate grid for adding pieces by hand.
"""
import argparse
import os
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def segment(T, min_area):
    h, w = T.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(T, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    bg = cv2.medianBlur(cv2.resize(T, (max(1, w // 16), max(1, h // 16))), 31)
    bg = cv2.resize(bg, (w, h))
    bgl = cv2.cvtColor(bg, cv2.COLOR_BGR2LAB).astype(np.float32)
    d = np.sqrt(((lab - bgl) ** 2).sum(axis=2))
    grey = cv2.cvtColor(T, cv2.COLOR_BGR2GRAY)
    e = cv2.dilate(cv2.Canny(grey, 60, 140), np.ones((3, 3), np.uint8)) > 0
    eb = cv2.dilate(cv2.Canny(grey, 30, 90), np.ones((3, 3), np.uint8)) > 0
    L = bgl[..., 0]
    glare = L > 165
    m = ((d > np.where(glare, 12, 22)) | (e & (d > 12)) | (eb & glare & (d > 7))).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    border = max(4, int(0.010 * max(h, w)))               # the table edge itself is not a piece
    m[:border] = 0; m[-border:] = 0; m[:, :border] = 0; m[:, -border:] = 0
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    def solidity(c):
        return cv2.contourArea(c) / max(1.0, cv2.contourArea(cv2.convexHull(c)))

    def clean(c):            # small pieces may be any shape; big ones must be a solid plate or wedge
        return solidity(c) >= (0.6 if cv2.contourArea(c) < 0.004 * h * w else 0.9)

    out = []
    for c in cs:
        a = cv2.contourArea(c)
        if not (min_area < a < 0.15 * h * w):
            continue
        if clean(c):
            out.append((c, True))
            continue
        x, y, ww, hh = cv2.boundingRect(c)
        sub = np.zeros((hh + 20, ww + 20), np.uint8)
        cv2.drawContours(sub, [c - [x - 10, y - 10]], -1, 255, -1)
        dist = cv2.distanceTransform(sub, cv2.DIST_L2, 5)
        _, peaks = cv2.threshold(dist, 0.45 * dist.max(), 255, 0)
        peaks = np.uint8(peaks)
        n, mk = cv2.connectedComponents(peaks)
        if n <= 2:
            out.append((c, False))
            continue
        mk = mk + 1
        mk[(sub > 0) & (peaks == 0)] = 0
        ws = cv2.watershed(cv2.cvtColor(sub, cv2.COLOR_GRAY2BGR), mk.astype(np.int32))
        for k in range(2, n + 1):
            pc, _ = cv2.findContours(np.uint8(ws == k) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for q in pc:
                if cv2.contourArea(q) > min_area:
                    out.append((q + [x - 10, y - 10], clean(q)))
    return out, bg


def register(closeup, photo):
    """Homography from a close-up to the overhead photo (full size), and its inlier count.

    The close-up is tried at a few sizes against the overhead photo at full size, so the
    features are compared at similar scales; the best match that passes the checks wins."""
    sift = cv2.SIFT_create(20000)

    def prep(im, long_side):
        k = min(1.0, long_side / max(im.shape[:2]))
        g = cv2.cvtColor(cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        kp, d = sift.detectAndCompute(g, None)
        return k, kp, d
    kp_, kpp, dp = prep(photo, 3000)
    best, best_n = None, 0
    for size in (1600, 1000, 640):
        kc_, kpc, dc = prep(closeup, size)
        if dc is None or dp is None:
            continue
        good = [m for m, n in (x for x in cv2.BFMatcher().knnMatch(dc, dp, k=2) if len(x) == 2) if m.distance < 0.75 * n.distance]
        if len(good) < 12:
            best_n = max(best_n, len(good))
            continue
        A = np.float32([kpc[m.queryIdx].pt for m in good]) / kc_
        B = np.float32([kpp[m.trainIdx].pt for m in good]) / kp_
        H, inl = cv2.findHomography(A, B, cv2.RANSAC, 8.0)
        n = int(inl.sum()) if inl is not None else 0
        best_n = max(best_n, n)
        if H is not None and n >= 30 and n > (best[1] if best else 0) and looks_right(closeup, photo, H):
            best = (H, n)
    return (best[0], best[1]) if best else (None, best_n)


def looks_right(closeup, photo, H):
    """A sane footprint, and the close-up laid onto the overhead photo looks like it there."""
    h, w = closeup.shape[:2]
    fp = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), H)
    share = cv2.contourArea(fp) / (photo.shape[0] * photo.shape[1])
    if not (0.005 < share < 0.8) or not cv2.isContourConvex(np.int32(fp)):
        return False
    k = 1000 / max(photo.shape[:2])
    S = np.diag([k, k, 1])
    size = (int(photo.shape[1] * k), int(photo.shape[0] * k))
    warped = cv2.warpPerspective(cv2.cvtColor(closeup, cv2.COLOR_BGR2GRAY), S @ H, size).astype(np.float32)
    mask = cv2.warpPerspective(np.full(closeup.shape[:2], 255, np.uint8), S @ H, size) > 0
    mask = cv2.erode(mask.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    ref = cv2.resize(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), size, interpolation=cv2.INTER_AREA).astype(np.float32)
    return ncc(warped[mask], ref[mask]) >= 0.6


def ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="brick-guide-work")
    ap.add_argument("--closeups", nargs="*", help="close-up photos of parts of the table (optional; kept for later runs)")
    a = ap.parse_args()
    work = C.work_dir(a.work)
    cfg = C.config(work)
    T = os.path.join(work, "table")
    cj = C.jread(os.path.join(T, "corners.json"))
    if not cj:
        C.die("run table.py first")
    flat = cv2.imread(os.path.join(T, "flat.jpg"))
    h, w = flat.shape[:2]
    q = np.float32(cj["corners"])
    side = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[3] - q[0]))
    k = max(w, h) / side                                     # flat pixels per photo pixel
    min_area = cfg["table"]["min_piece_px"] * k * k
    cap = cfg["brickognize"]["max_side_px"]

    # close-ups: register each to the overhead photo once
    cdir = os.path.join(T, "closeups")
    if a.closeups is not None:
        shutil.rmtree(cdir, ignore_errors=True)
        os.makedirs(cdir)
        for f in a.closeups:
            if not os.path.exists(f):
                C.die(f"no such file: {f}")
            shutil.copy(f, os.path.join(cdir, os.path.basename(f)))
    closeups = []
    if os.path.isdir(cdir) and os.listdir(cdir):
        photo = C.load_photo(os.path.join(work, cj["photo"]))
        Hfp = np.linalg.inv(np.array(cj["H"]))                  # flat -> photo
        for f in sorted(os.listdir(cdir)):
            im = C.load_photo(os.path.join(cdir, f))
            H, n = register(im, photo)
            if H is None:
                print(f"close-up {f}: does not match the overhead photo ({n} matching points; taken at another time?); skipped")
                continue
            closeups.append(dict(name=f, im=im, Hfc=np.linalg.inv(H) @ Hfp))
            print(f"close-up {f}: matched ({n} points)")

    def from_closeup(x0, y0, cw, ch):
        """The best close-up view of a flat-table rectangle: (close-up, pixels per flat pixel)."""
        best = None
        box = np.float32([[x0, y0], [x0 + cw, y0], [x0 + cw, y0 + ch], [x0, y0 + ch]]).reshape(-1, 1, 2)
        for cu in closeups:
            q = cv2.perspectiveTransform(box, cu["Hfc"]).reshape(-1, 2)
            hh, ww = cu["im"].shape[:2]
            if q.min() < 5 or (q[:, 0] > ww - 5).any() or (q[:, 1] > hh - 5).any():
                continue
            k_ = np.sqrt(cv2.contourArea(q) / max(1.0, cw * ch))
            if k_ >= 1.3 and (best is None or k_ > best[1]):
                best = (cu, k_)
        return best

    found, bgimg = segment(flat, min_area)
    found.sort(key=lambda t: (cv2.boundingRect(t[0])[1] // 150, cv2.boundingRect(t[0])[0]))   # rows, left to right
    crops = os.path.join(T, "crops")
    os.makedirs(crops, exist_ok=True)
    for f in os.listdir(crops):
        os.remove(os.path.join(crops, f))
    pieces = []
    for i, (c, ok) in enumerate(found, 1):
        x, y, bw, bh = cv2.boundingRect(c)
        M = cv2.moments(c)
        cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]
        pad = int(0.18 * max(bw, bh)) + 10
        x0, y0 = max(0, x - pad), max(0, y - pad)
        crop = flat[y0:y + bh + pad, x0:x + bw + pad].copy()
        others = np.zeros(crop.shape[:2], np.uint8)          # paint out every other piece: one brick per crop
        for j, (c2, _) in enumerate(found):
            if j != i - 1:
                cv2.drawContours(others, [c2 - [x0, y0]], -1, 255, -1)
        mine = np.zeros(crop.shape[:2], np.uint8)
        cv2.drawContours(mine, [c - [x0, y0]], -1, 255, -1)
        others = cv2.dilate(others, np.ones((9, 9), np.uint8)) & ~cv2.dilate(mine, np.ones((5, 5), np.uint8))
        fill = bgimg[y0:y0 + crop.shape[0], x0:x0 + crop.shape[1]]
        src = "overhead"
        cu = from_closeup(x0, y0, crop.shape[1], crop.shape[0])
        if cu:                                              # a sharper view of the same piece
            kk = min(cu[1], cap / max(crop.shape[:2]))
            size = (max(1, int(crop.shape[1] * kk)), max(1, int(crop.shape[0] * kk)))
            Mx = cu[0]["Hfc"] @ np.array([[1, 0, x0], [0, 1, y0], [0, 0, 1]]) @ np.diag([1 / kk, 1 / kk, 1])
            sharp = cv2.warpPerspective(cu[0]["im"], Mx, size, flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
            g1 = cv2.cvtColor(cv2.resize(sharp, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
            g2 = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
            if ncc(g1, g2) >= 0.6:                          # the same piece, seen closer: use it
                crop = sharp
                others = cv2.resize(others, size, interpolation=cv2.INTER_NEAREST)
                fill = cv2.resize(fill, size, interpolation=cv2.INTER_LINEAR)
                src = cu[0]["name"]
        crop[others > 0] = fill[others > 0]
        if max(crop.shape[:2]) > cap:                       # a single piece, never a big picture
            s = cap / max(crop.shape[:2])
            crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        f = os.path.join(crops, f"{i:03d}.jpg")
        cv2.imwrite(f, crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        pieces.append(dict(id=i, at=[round(cx, 1), round(cy, 1)], box=[x, y, bw, bh], area=float(cv2.contourArea(c)),
                           r=round(0.6 * np.sqrt(cv2.contourArea(c)) + 4, 1), big=not ok, crop=os.path.relpath(f, work), src=src))
    C.jwrite(os.path.join(T, "pieces.json"), dict(flat_size=[w, h], pieces=pieces))

    mp = flat.copy()
    for p in pieces:
        col = (40, 40, 230) if p["big"] else (0, 220, 255)
        cv2.circle(mp, (int(p["at"][0]), int(p["at"][1])), int(p["r"] + 6), col, 4)
        cv2.putText(mp, str(p["id"]), (int(p["at"][0] + p["r"]), int(p["at"][1] - p["r"])), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 6)
        cv2.putText(mp, str(p["id"]), (int(p["at"][0] + p["r"]), int(p["at"][1] - p["r"])), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
    cv2.imwrite(os.path.join(T, "pieces-map.jpg"), mp, [cv2.IMWRITE_JPEG_QUALITY, 85])
    g = flat.copy()
    step = 200
    for x in range(0, w, step):
        cv2.line(g, (x, 0), (x, h), (255, 255, 0), 2)
        cv2.putText(g, str(x), (x + 4, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 3)
    for y in range(0, h, step):
        cv2.line(g, (0, y), (w, y), (255, 255, 0), 2)
        cv2.putText(g, str(y), (4, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 3)
    cv2.imwrite(os.path.join(T, "grid.jpg"), g, [cv2.IMWRITE_JPEG_QUALITY, 85])
    nb = sum(p["big"] for p in pieces)
    if closeups:
        print(f"{sum(p['src'] != 'overhead' for p in pieces)} crops cut from close-ups")
    print(f"{len(pieces)} pieces found, {nb} flagged big or lumpy (for Claude to look at)")
    print("next: identify.py")


if __name__ == "__main__":
    main()
