"""Shared helpers: the work folder, settings, photos, colours, fonts and contact sheets.

Everything the scripts make lives in one work folder (default ./brick-guide-work):

    config.json          your settings (copied from config.example.json on first run)
    book/                what book.py read from the instruction PDF
    table/               the table photo, its corners, the flattened table, the pieces
    brickognize/         only if you opted in: cache.json and sent.log
    review/              sheets for the Claude check, and review.json with its answers
    site/                the build guide (open site/index.html)
"""
import copy
import hashlib
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

DEFAULTS = {
    "brickognize": {
        "enabled": False,
        "endpoint": "https://api.brickognize.com/predict/parts/",
        "max_side_px": 600,
        "timeout_s": 45,
        "pause_s": 0.6,
        "send_parts_list_drawings": True,
    },
    "review": {
        "min_score": 0.60,
        "tie_margin": 0.05,
        "drawing_gap": 0.30,
    },
    "table": {
        "flat_long_side_px": 3400,
        "min_piece_px": 250,
    },
    "site": {
        "title": "",
        "storage_prefix": "bbg:",
    },
}


def die(msg, code=1):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def work_dir(path):
    path = os.path.abspath(path or "brick-guide-work")
    os.makedirs(path, exist_ok=True)
    return path


def merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        elif not k.startswith("_"):
            out[k] = v
    return out


def config(work):
    """Settings: the defaults above, overlaid with WORK/config.json (created on first use)."""
    f = os.path.join(work, "config.json")
    if not os.path.exists(f):
        src = os.path.join(SKILL, "config.example.json")
        with open(src) as a, open(f, "w") as b:
            b.write(a.read())
    return merge(DEFAULTS, jread(f))


def jread(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def jwrite(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def load_photo(path):
    """A photo as BGR, turned upright using its EXIF orientation."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def to_pil(bgr):
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def lab(bgr):
    return cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)


def border_colour(im):
    """Median colour of an image's outer pixels: its background."""
    edge = np.concatenate([im[0], im[-1], im[:, 0], im[:, -1]])
    return np.median(edge, axis=0)


def foreground(im, tol=40):
    """Mask of pixels that differ from the background colour (border median)."""
    bg = border_colour(im).astype(float)
    return np.abs(im.astype(float) - bg).sum(axis=2) > tol


def piece_colour(im, tol=40):
    """Median BGR colour of the piece in a crop: the middle of the crop, minus the background."""
    h, w = im.shape[:2]
    mid = im[int(h * .2):int(h * .8) + 1, int(w * .2):int(w * .8) + 1]
    m = foreground(im, tol)[int(h * .2):int(h * .8) + 1, int(w * .2):int(w * .8) + 1]
    px = mid[m] if m.sum() > 20 else mid.reshape(-1, 3)
    return np.median(px, axis=0)


def colour_name(bgr):
    """A plain colour word for a BGR colour, for labels. Approximate on purpose."""
    hsv = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0, 0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
    if v < 60:
        return "black"
    if s < 60:
        return "white" if v > 200 else ("light grey" if v > 135 else "dark grey")
    if h < 8 or h > 170:
        return "dark red" if v < 150 else "red"
    if h < 20:
        return "tan" if s < 130 else "orange"
    if h < 35:
        return "yellow"
    if h < 85:
        return "green"
    if h < 130:
        return "blue"
    return "purple"


_fonts = {}


def font(size, bold=True):
    """A TrueType font if one is installed, else Pillow's built-in one."""
    key = (size, bold)
    if key not in _fonts:
        names = (["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf"] if bold
                 else ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "LiberationSans-Regular.ttf"])
        dirs = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",
                "/Library/Fonts", "/System/Library/Fonts/Supplemental", "C:/Windows/Fonts", ""]
        f = None
        for d in dirs:
            for n in names:
                try:
                    f = ImageFont.truetype(os.path.join(d, n) if d else n, size)
                    break
                except OSError:
                    continue
            if f:
                break
        _fonts[key] = f or ImageFont.load_default(size=size)
    return _fonts[key]


def contact_sheet(tiles, path, cols=6, cell=220, caption_h=46, cell_h=None):
    """Save a grid of (image BGR or PIL, caption) tiles as one JPEG, for the Claude check.

    Returns the path. Captions are drawn under each tile in large type so a reader can
    quote them back (the number is what review.json refers to)."""
    ch = cell_h or cell
    rows = max(1, -(-len(tiles) // cols))
    sheet = Image.new("RGB", (cols * cell, rows * (ch + caption_h)), "white")
    d = ImageDraw.Draw(sheet)
    for i, (im, cap) in enumerate(tiles):
        if not isinstance(im, Image.Image):
            im = to_pil(im)
        im = im.copy()
        im.thumbnail((cell - 10, ch - 10))
        x, y = (i % cols) * cell, (i // cols) * (ch + caption_h)
        sheet.paste(im, (x + (cell - im.size[0]) // 2, y + (ch - im.size[1]) // 2))
        d.rectangle([x, y, x + cell - 1, y + ch + caption_h - 1], outline="#bbbbbb")
        size = 18                                   # shrink a long caption to fit its tile
        while size > 10 and d.textlength(cap, font=font(size)) > cell - 12:
            size -= 1
        d.text((x + 6, y + ch + 4), cap, fill="black", font=font(size))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path, quality=88)
    return path
