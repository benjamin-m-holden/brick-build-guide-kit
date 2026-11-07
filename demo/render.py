"""Tiny z-buffered polygon renderer for the brick demo. No outside assets.

A part is a list of planar 3-D polygons, each with a colour and a group id (faces in
one group get no outline between them, e.g. the side of a cylinder). Units: one stud
= 1 in x and y; a brick is 1.2 tall, a plate 0.4.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BRICK, PLATE = 1.2, 0.4
STUD_R, STUD_H = 0.3, 0.17
_gid = [0]


def gid():
    _gid[0] += 1
    return _gid[0]


def hexrgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def box(x0, y0, z0, w, d, h, col):
    x1, y1, z1 = x0 + w, y0 + d, z0 + h
    P = []
    for quad in ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                 [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
                 [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
                 [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
                 [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
                 [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]):
        P.append((quad, col, gid()))
    return P


def cyl_z(cx, cy, z0, r, h, col, n=20, cap=True):
    """Vertical cylinder (studs, round bricks)."""
    ang = [2 * math.pi * i / n for i in range(n)]
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in ang]
    g = gid(); P = []
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        P.append(([(ax, ay, z0), (bx, by, z0), (bx, by, z0 + h), (ax, ay, z0 + h)], col, g))
    if cap:
        P.append(([(x, y, z0 + h) for x, y in pts], col, gid()))
    return P


def studs(x0, y0, z, w, d, col):
    P = []
    for i in range(w):
        for j in range(d):
            P += cyl_z(x0 + i + .5, y0 + j + .5, z, STUD_R, STUD_H, col, n=16)
    return P


def cyl_y(cx, cz, y0, y1, r, col, hub=None, n=28):
    """Wheel: cylinder whose axis runs along y."""
    ang = [2 * math.pi * i / n for i in range(n)]
    pts = [(cx + r * math.cos(a), cz + r * math.sin(a)) for a in ang]
    g = gid(); P = []
    for i in range(n):
        (ax, az), (bx, bz) = pts[i], pts[(i + 1) % n]
        P.append(([(ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az)], col, g))
    for yy in (y0, y1):
        P.append(([(x, yy, z) for x, z in pts], col, gid()))
        if hub:
            for rr, c in ((r * .62, hub), (r * .2, '#55595e')):
                hp = [(cx + rr * math.cos(a), cz + rr * math.sin(a)) for a in ang]
                e = .01 if yy == y1 else -.01
                e *= 2 if rr < r * .5 else 1
                P.append(([(x, yy + e, z) for x, z in hp], c, gid()))
    return P


def slope(x0, y0, z0, d, col):
    """45-degree slope 2 long (falling toward +x), d wide, one stud row at the back."""
    h, lip = BRICK, .35
    xs = [(x0, z0), (x0 + 2, z0), (x0 + 2, z0 + lip), (x0 + 1, z0 + h), (x0, z0 + h)]
    y1 = y0 + d; P = []
    P.append(([(x, y0, z) for x, z in xs], col, gid()))
    P.append(([(x, y1, z) for x, z in xs], col, gid()))
    P.append(([(x0, y0, z0), (x0, y1, z0), (x0, y1, z0 + h), (x0, y0, z0 + h)], col, gid()))
    P.append(([(x0, y0, z0 + h), (x0 + 1, y0, z0 + h), (x0 + 1, y1, z0 + h), (x0, y1, z0 + h)], col, gid()))
    P.append(([(x0 + 1, y0, z0 + h), (x0 + 2, y0, z0 + lip), (x0 + 2, y1, z0 + lip), (x0 + 1, y1, z0 + h)], col, gid()))
    P.append(([(x0 + 2, y0, z0), (x0 + 2, y1, z0), (x0 + 2, y1, z0 + lip), (x0 + 2, y0, z0 + lip)], col, gid()))
    P += studs(x0, y0, z0 + h, 1, d, col)
    return P


# ---------- part kinds ----------
def make(kind, x, y, z, col, **k):
    w, d = k.get('w', 1), k.get('d', 1)
    if kind in ('brick', 'plate', 'tile'):
        h = BRICK if kind == 'brick' else PLATE
        P = box(x, y, z, w, d, h, col)
        if kind != 'tile':
            P += studs(x, y, z + h, w, d, col)
        return P
    if kind == 'round':      # 1x1 round brick or plate
        h = k.get('h', BRICK)
        return cyl_z(x + .5, y + .5, z, .5, h, col) + cyl_z(x + .5, y + .5, z + h, STUD_R, STUD_H, col, n=16)
    if kind == 'slope':
        return slope(x, y, z, d, col)
    if kind == 'wheel':      # x,z = axle centre; y = inner face; d = width
        return cyl_y(x, z, y, y + d, k.get('r', 1.05), col, hub=k.get('hub', '#c9ccd1'))
    raise ValueError(kind)


# ---------- transforms ----------
def rot_z(P, ang, cx, cy):
    c, s = math.cos(ang), math.sin(ang)
    return [([(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c, z) for x, y, z in q], col, g)
            for q, col, g in P]


def move(P, dx, dy, dz):
    return [([(x + dx, y + dy, z + dz) for x, y, z in q], col, g) for q, col, g in P]


def bounds(P):
    a = np.array([v for q, _, _ in P for v in q])
    return a.min(0), a.max(0)


# ---------- projections ----------
C30, S30 = math.cos(math.pi / 6), math.sin(math.pi / 6)


def iso(v):            # (u, v, depth); larger depth is nearer
    x, y, z = v
    return (x - y) * C30, (x + y) * S30 - z, x + y + z


def overhead(v):       # camera above the table, tipped a little toward the viewer
    x, y, z = v
    return x, y - .32 * z, z + .02 * y


LIGHT = np.array([.25, .55, 1.0]); LIGHT /= np.linalg.norm(LIGHT)


def _normal(q):
    a = np.array(q, float); n = np.zeros(3)
    for i in range(len(a)):
        n += np.cross(a[i], a[(i + 1) % len(a)])
    L = np.linalg.norm(n)
    return n / L if L else n


def render(P, proj=iso, scale=60, pad=10, size=None, origin=None, ss=2, outline=(30, 32, 36), light=LIGHT,
           bg=None):
    """Return an RGBA image. size+origin fix the framing (so steps of one model line up)."""
    pr = [[proj(v) for v in q] for q, _, _ in P]
    U = np.array([p[0] for ps in pr for p in ps]); V = np.array([p[1] for ps in pr for p in ps])
    S = scale * ss
    if size is None:
        u0, v0 = U.min() * S - pad * ss, V.min() * S - pad * ss
        W, H = int(U.max() * S - u0 + pad * ss) + 1, int(V.max() * S - v0 + pad * ss) + 1
    else:
        W, H = size[0] * ss, size[1] * ss
        u0, v0 = origin[0] * ss, origin[1] * ss
    zb = np.full((H, W), -1e9); col = np.zeros((H, W, 3)); ids = np.zeros((H, W), np.int32)
    for (q, c, g), ps in zip(P, pr):
        n = _normal(q)
        if np.allclose(n, 0): continue
        xy = [(p[0] * S - u0, p[1] * S - v0) for p in ps]
        xs = [a for a, _ in xy]; ys = [b for _, b in xy]
        bx0, by0 = max(0, int(min(xs))), max(0, int(min(ys)))
        bx1, by1 = min(W - 1, int(max(xs)) + 1), min(H - 1, int(max(ys)) + 1)
        if bx1 < bx0 or by1 < by0: continue
        A = np.array([[a, b, 1] for a, b in xy]); dz = np.array([p[2] for p in ps])
        if np.linalg.matrix_rank(A, tol=1e-3) < 3: continue        # seen edge-on
        coef = np.linalg.lstsq(A, dz, rcond=None)[0]
        m = Image.new('L', (bx1 - bx0 + 1, by1 - by0 + 1)); ImageDraw.Draw(m).polygon([(a - bx0, b - by0) for a, b in xy], fill=1)
        m = np.asarray(m).astype(bool)
        if not m.any(): continue
        yy, xx = np.nonzero(m); X = xx + bx0; Y = yy + by0
        d = coef[0] * X + coef[1] * Y + coef[2]
        k = d > zb[Y, X]
        X, Y, d = X[k], Y[k], d[k]
        zb[Y, X] = d; ids[Y, X] = g
        sh = .5 + .55 * max(0.0, float(np.dot(n, light))) if np.dot(n, light) >= 0 else .5
        sh = min(sh, 1.06)
        rgb = np.array(hexrgb(c), float)
        col[Y, X] = np.clip(rgb * sh + (12 if sh > 1 else 0), 0, 255)
    alpha = (ids > 0)
    if outline is not None:
        e = np.zeros_like(alpha)
        e[:, :-1] |= ids[:, :-1] != ids[:, 1:]; e[:-1, :] |= ids[:-1, :] != ids[1:, :]
        e = np.asarray(Image.fromarray((e * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        e &= alpha | np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        col[e] = outline; alpha = alpha | e
    im = np.dstack([col, alpha * 255]).astype(np.uint8)
    out = Image.fromarray(im, 'RGBA').resize((W // ss, H // ss), Image.LANCZOS)
    if bg:
        b = Image.new('RGBA', out.size, bg); b.alpha_composite(out); out = b
    return out


def frame_of(P, proj=iso, scale=60, pad=10):
    """Size and origin that fit P; reuse them to draw earlier steps of the same model."""
    pr = [proj(v) for q, _, _ in P for v in q]
    U = np.array([p[0] for p in pr]); V = np.array([p[1] for p in pr])
    u0, v0 = U.min() * scale - pad, V.min() * scale - pad
    return (int(U.max() * scale - u0 + pad) + 1, int(V.max() * scale - v0 + pad) + 1), (u0, v0)
