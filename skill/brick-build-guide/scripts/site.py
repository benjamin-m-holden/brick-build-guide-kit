"""Build the phone guide: Setup, Inventory, and the book pages you ask for.

    python site.py --work WORK --pages 6-7      # add pages 6 and 7 (keeps pages built before)
    python site.py --work WORK                  # rebuild what is there (after new answers or photos)
    python site.py --work WORK --all            # every page with steps

Build a couple of pages at a time: the table changes as pieces get used, so retake the
photo every few pages and rerun the table steps; identification is cached and reused.

Writes WORK/site/index.html and its pictures. It is one static page: open it on your
computer, or serve the folder on your home network to open it on a phone.
It shows pages of your instruction book, so keep it for your own use; do not publish it.
"""
import argparse
import collections
import html
import json
import os
import re
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

esc = html.escape
COL = ["#ff2fb3", "#ffb000", "#00b7ff", "#3ccf00", "#ff6a00", "#ff3b3b", "#9b6bff", "#00c9a7"]
SETUP, INVENTORY = -2, -1
ANY = '<span class="tag zipf">any of them will do</span>'
DISPLAY_DPI = 150


class Site:
    def __init__(self, work, out):
        self.work, self.out = work, out
        self.v = int(time.time())
        os.makedirs(out, exist_ok=True)

    def save(self, im, name, maxw=1600, q=84):
        if not isinstance(im, Image.Image):
            im = C.to_pil(im)
        im = im.copy()
        im.thumbnail((maxw, maxw * 3))
        f = os.path.join(self.out, name)
        if name.endswith(".png"):
            im.save(f, optimize=True)
        else:
            im.convert("RGB").save(f, quality=q, optimize=True, progressive=True)
        return f"{name}?v={self.v}"


def parse_pages(s):
    out = set()
    for part in (s or "").split(","):
        if part.strip():
            a, _, b = part.partition("-")
            out |= set(range(int(a), int(b or a) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="brick-guide-work")
    ap.add_argument("--pages", help="book pages to add, e.g. 6-7 or 6,9-10")
    ap.add_argument("--all", action="store_true", help="every page that has steps")
    ap.add_argument("--demo-note", help=argparse.SUPPRESS)
    a = ap.parse_args()
    work = C.work_dir(a.work)
    cfg = C.config(work)
    book = C.jread(os.path.join(work, "book", "book.json"))
    mt = C.jread(os.path.join(work, "table", "matched.json"))
    if not (book and mt):
        C.die("run book.py, table.py, pieces.py, identify.py and match.py first")
    out = os.path.join(work, "site")
    S = Site(work, out)
    state = C.jread(os.path.join(out, "state.json"), {"built": []})

    parts, items = book["parts"], book["items"]
    names, bags = book.get("names", {}), {int(k): v for k, v in book.get("bags", {}).items()}
    step_pages = sorted({it["page"] for it in items} | {int(p) for p in book["main_steps"]})
    built = set(state["built"]) | parse_pages(a.pages)
    if a.all:
        built |= set(step_pages)
    bad = sorted(built - set(step_pages))
    if bad:
        print(f"skipping pages without steps: {bad}")
    built = sorted(built & set(step_pages))
    state["built"] = built
    title = cfg["site"]["title"] or re.sub(r"[_-]+", " ", os.path.splitext(os.path.basename(book["pdf"]))[0]).strip().title()

    def bag(page):
        b = [v for p, v in sorted(bags.items()) if p <= page]
        return b[-1] if b else None

    def bagtag(page):
        b = bag(page)
        return f'<span class="tag bag">Bag {b}</span>' if b else ""

    pieces = {p["id"]: p for p in mt["pieces"]}
    found = {el: ids for el, ids in mt["found"].items()}
    uses = collections.defaultdict(list)            # element -> [[page, step, count, item]]
    for it in items:
        if it.get("element"):
            uses[it["element"]].append([it["page"], it["step"], it["count"], it])
    need = {el: p["count"] for el, p in parts.items()}

    # ---- part pictures and names
    noimg = Image.new("RGB", (200, 200), "#e3e3e3")
    ImageDraw.Draw(noimg).text((100, 100), "No image", fill="#888", font=C.font(20, False), anchor="mm")
    S.save(noimg, "noimg.png", 200)
    pic, cname = {}, {}

    def part_img(el):
        if el not in pic:
            f = os.path.join(work, parts[el]["img"]) if el in parts else None
            im = cv2.imread(f) if f and os.path.exists(f) else None
            if im is None and found.get(el):                 # no drawing: your own photo of it
                im = cv2.imread(os.path.join(work, pieces[found[el][0]]["crop"]))
            pic[el] = S.save(im, f"part-{el}.jpg", 360) if im is not None else "noimg.png"
            cname[el] = C.colour_name(C.piece_colour(im)) if im is not None else ""
        return pic[el]

    def part_name(el):
        part_img(el)
        n = names.get(el)
        return n if n else (f"{cname[el].capitalize()} part" if cname.get(el) else "Part")

    # ---- table maps
    flat = Image.open(os.path.join(work, "table", "flat.jpg")).convert("RGB")
    FW = flat.size[0]
    dim = Image.blend(flat, Image.new("RGB", flat.size, (0, 0, 0)), 0.28)
    mapsrc = {}

    def table_map(el):
        if el not in mapsrc:
            mp = dim.copy()
            d = ImageDraw.Draw(mp)
            k = FW / 1600
            for n, i in enumerate(dict.fromkeys(found.get(el, [])), 1):
                q = pieces[i]
                x, y, r = q["at"][0], q["at"][1], q["r"] + 10 * k
                for t in range(int(6 * k) + 3):
                    d.ellipse([x - r - t, y - r - t, x + r + t, y + r + t], outline=(255, 214, 0))
                d.text((x + r + 4, y - r - 30 * k), str(n), fill=(255, 214, 0), font=C.font(int(34 * k)), stroke_width=int(4 * k), stroke_fill="black")
            mapsrc[el] = S.save(mp, f"map-{el}.jpg", 1400)
        return mapsrc[el]

    # ---- book pages at display size, with each label's drawing ringed
    pdir = os.path.join(work, "book", f"pages{DISPLAY_DPI}")
    os.makedirs(pdir, exist_ok=True)

    def page_png(p):
        f = os.path.join(pdir, f"p-{p:03d}.png")
        if not os.path.exists(f):
            subprocess.run(["pdftoppm", "-r", str(DISPLAY_DPI), "-png", "-singlefile", "-f", str(p), "-l", str(p), book["pdf"], f[:-4]],
                           check=True, capture_output=True)
        return Image.open(f).convert("RGB")

    k = DISPLAY_DPI / book["dpi"]

    def ring(d, it, colour, width=4, label=None):
        x, y, w, h = [v * k for v in it["draw"]]
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2 + 14, h / 2 + 12
        for t in range(width):
            d.ellipse([cx - rx - t, cy - ry - t, cx + rx + t, cy + ry + t], outline=colour)
        if label:
            d.text((cx + rx - 6, cy - ry - 30), label, fill=colour, font=C.font(28), stroke_width=4, stroke_fill="black")

    # ---- step pages
    by_page = collections.defaultdict(list)
    for it in items:
        by_page[it["page"]].append(it)
    pages_html, ranges = {}, {}
    for pg in built:
        its = by_page.get(pg, [])
        steps = [int(s) for s in book["main_steps"].get(str(pg), [])]
        for it in its:
            if it["step"] not in steps:
                steps.append(it["step"])
        cont = not steps
        if cont:
            steps = [book["last_step"].get(str(pg)) or 1]
        steps = sorted(set(steps))
        im = page_png(pg)
        d = ImageDraw.Draw(im)
        for it in its:
            ring(d, it, COL[(ord(it["label"][-1]) - 97) % len(COL)], label=it["label"])
        psrc = S.save(im, f"book-p{pg}.jpg", 1400)
        cards = ""
        for st in steps:
            rows = ""
            mine = [it for it in its if it["step"] == st]
            for it in mine:
                el, L = it.get("element"), it["label"]
                nf = len(found.get(el, [])) if el else 0
                b = bag(pg)
                maptag = (f'<img class="pmap" data-zoom src="{table_map(el)}" loading="lazy" alt="The table, with every matching piece ringed">' if nf
                          else f'<div class="nf">Not found in your photo.{"<br>Check bag " + str(b) + "." if b else ""}</div>')
                unsure = ('<span class="tag maybe">unsure: check the picture</span>' if it.get("how") not in ("checked", "confirmed")
                          and (it["gap"] < cfg["review"]["drawing_gap"] or it.get("how") == "disagree") else "")
                rows += (f'<div class="part arow" data-el="{esc(str(el))}"><div class="phead"><label class="chk"><input type="checkbox" data-k="p{pg}-{L}"><span class="box"></span>'
                         f'<b class="lab" style="--c:{COL[(ord(L[-1]) - 97) % len(COL)]}">{L}</b></label>'
                         f'<a class="toinv pname" href="#part-{esc(str(el))}" data-el="{esc(str(el))}">{esc(part_name(el)) if el else "?"}</a><span class="pcnt">{it["count"]}&times;</span>'
                         f'<button class="pexp" aria-label="Show details">&#8250;</button></div><div class="pfold"><div>'
                         f'<div class="ids eln">element {esc(str(el))}</div>'
                         f'<div class="tags">{bagtag(pg)}<span class="tag {"ok" if nf else "none"}">Found {nf}</span>'
                         f'{ANY if nf > 1 else ""}{unsure}</div>'
                         f'<div class="apics"><img class="draw" src="{part_img(el) if el else "noimg.png"}" loading="lazy" alt="">{maptag}</div></div></div></div>')
            key = f"p{pg}-step{st}{'c' if cont else ''}"
            n_ = len(mine)
            cards += (f'<article class="step" id="step-{pg}-{st}" data-k="{key}"><div class="sh"><button class="open" aria-expanded="true"><span class="sn">Step {st}</span><span class="pgtag">page {pg}</span>'
                      f'<span class="meta">{(str(n_) + " part" + ("s" if n_ != 1 else "")) if n_ else "no new parts"}</span><span class="chev">&#8250;</span></button>'
                      f'<label class="done"><input type="checkbox" data-k="{key}" class="stepdone"><span class="box"></span>Done</label></div>'
                      f'<div class="body"><div class="inner">{rows or "<p class=ids>No new parts: follow the picture.</p>"}<button class="upto stepbtn">&#10003; Done up to here</button></div></div></article>')
        rng = str(steps[0]) if len(steps) == 1 else f"{steps[0]}–{steps[-1]}"
        ranges[pg] = rng
        head = ("Step " + rng + (", continued" if cont else "")) if len(steps) == 1 else "Steps " + rng
        b = bag(pg)
        pages_html[pg] = (f'<section class="pg" data-page="{pg}" hidden><h2>{esc(head)} <small>Page {pg} of the book{" &middot; bag " + str(b) if b else ""}</small></h2>'
                          f'<button class="upto pagebtn">&#10003; Mark all earlier pages done</button><img class="bookpage" data-zoom src="{psrc}" loading="lazy" alt="Page {pg} of the instructions, each new part ringed and labelled">{cards}</section>')

    # ---- inventory
    rows_in = ""
    for el in sorted(parts, key=lambda e: (-need[e], e)):
        seen = len(found.get(el, []))
        u = sorted(uses.get(el, []), key=lambda x: (x[0], x[1]))
        usum = sum(x[2] for x in u)
        cls = "ok" if seen >= need[el] else ("part" if seen else "none")
        warn = "" if usum == need[el] else f'<span class="warn">steps found add up to {usum}, parts list says {need[el]}</span>'
        steprows = ""
        for pg, st, n, it in u:
            inb = pg in built
            im = page_png(pg) if inb else None
            thumb = ""
            if im is not None:
                ring(ImageDraw.Draw(im), it, (255, 40, 160), 5)
                thumb = f'<img class="spage" data-zoom src="{S.save(im, "use-" + it["id"] + ".jpg", 760)}" loading="lazy" alt="">'
            steprows += (f'<div class="sblock">{thumb}<a class="srow use{" built" if inb else ""}" href="{"#step-%d-%d" % (pg, st) if inb else "#"}" data-pg="{pg}" data-st="{st}" data-el="{el}" '
                         f'data-k="p{pg}-step{st}" data-n="{n}"><span><b>Page {pg} · Step {st}</b><small>{"Go to this step" if inb else "Not in the guide yet: page " + str(pg) + " of your PDF"}</small></span><em>{n}&times;</em><i>&#8250;</i></a></div>')
        fb = bag(u[0][0]) if u else None
        fmap = (f'<img class="tmap" data-zoom src="{table_map(el)}" loading="lazy" alt="">' if seen
                else f'<span class="ids">None found in your photo.{" Check bag " + str(fb) + "." if fb else ""}</span>')
        pn = names.get(el) and ""
        det = (f'<div class="det"><div class="hero"><img class="heroimg" src="{part_img(el)}" alt=""></div>'
               f'<h3>{esc(part_name(el))}</h3><div class="meta">element <b>{esc(el)}</b>{pn}</div>'
               + (f'<div class="bagline">From <b>bag {fb}</b> (first used on page {u[0][0]})</div>' if fb else "")
               + f'<div class="cards"><div><b>{need[el]}</b><small>In the set</small></div><div class="c-{cls}"><b>{seen}</b><small>Found</small></div><div><b class="used">0</b><small>Used so far</small></div><div><b class="left" data-need="{need[el]}">{need[el]}</b><small>Still to use</small></div></div>'
               f'<div class="pbar"><i class="pfill"></i></div>{warn}'
               f'<h4>Where they are on the table</h4><div class="fmap">{fmap}</div>'
               f'<h4>Used in these steps</h4><div class="srows">{steprows or "<span class=ids>Not in any parts box in the book (a spare, or a part the scripts did not place).</span>"}</div>'
               f'<h4>Look it up</h4><div class="links"><a href="https://rebrickable.com/search/?q={esc(el)}" target="_blank" rel="noopener">Rebrickable</a>'
               f'<a href="https://www.bricklink.com/v2/search.page?q={esc(el)}" target="_blank" rel="noopener">BrickLink</a></div></div>')
        useskeys = " ".join(f"p{pg}s{st}" for pg, st, _, _ in u)
        rows_in += (f'<button class="ir" id="inv-{esc(el)}" data-el="{esc(el)}" data-uses="{useskeys}" data-name="{esc(part_name(el).lower())} {esc(el.lower())}" data-need="{need[el]}" data-seen="{seen}">'
                    f'<img src="{part_img(el)}" loading="lazy" decoding="async" alt="{esc(part_name(el))}"><span class="tn"><i>{need[el]}<small>set</small></i><i class="t-{cls}">{seen}<small>found</small></i><i><span class="used">0</span><small>used</small></i></span>{det}</button>')
    strays = collections.defaultdict(list)
    for p in mt["pieces"]:
        if p["status"] == "notinset":
            key = (p["bk"][0][0], p["bk"][0][1]) if p.get("bk") else ("?", "not identified")
            strays[key].append(p)
    rows_out = "".join(f'<div class="ir"><img src="{S.save(cv2.imread(os.path.join(work, ps[0]["crop"])), "stray-" + str(ps[0]["id"]) + ".jpg", 200)}" loading="lazy" alt="">'
                       f'<div class="ib"><b>{esc(n)}</b><div class="ids">part {esc(pid)}</div><div class="nums"><span>Found <b>{len(ps)}</b></span></div></div></div>'
                       for (pid, n), ps in sorted(strays.items(), key=lambda x: -len(x[1])))
    allg = collections.Counter((p["bk"][0][1], p["bk"][0][0]) for p in mt["pieces"] if p.get("bk") and p["status"] != "ignored")
    rows_all = "".join(f"<tr><td>{esc(n)}</td><td>{esc(i)}</td><td>{c}</td></tr>" for (n, i), c in allg.most_common())
    pg_opts = "".join(f'<option value="{p}">Page {p}</option>' for p in sorted({x[0] for v in uses.values() for x in v}))
    st_opts = "".join(f'<option value="{s}">Step {s}</option>' for s in sorted({x[1] for v in uses.values() for x in v}))
    inv_html = ('<section class="pg" data-page="-1" hidden><h2>Inventory <small>Every part: what the set needs, what was found, and where it is used</small></h2>'
                '<div class="card" style="padding:10px"><input id="q" aria-label="Search parts" placeholder="Search: name or element ID" style="width:100%;font:inherit;padding:10px;border:1px solid #d5dae0;border-radius:10px">'
                '<details class="fmenu"><summary>Filter: all ▾</summary><div class="fpanel"><label><input type="checkbox" value="all"><span class="fdot" style="background:#2e7d32"></span>Found all</label><label><input type="checkbox" value="some"><span class="fdot" style="background:#b26b00"></span>Found some</label><label><input type="checkbox" value="none"><span class="fdot" style="background:#b42318"></span>Not found</label></div></details>'
                f'<div class="sel"><select id="fpg" aria-label="Page"><option value="">Any page</option>{pg_opts}</select><select id="fst" aria-label="Step"><option value="">Any step</option>{st_opts}</select></div></div>'
                '<div class="tnhead"><span>set</span><span>found</span><span>used</span></div>'
                f'<div id="invlist">{rows_in}</div><div class="fs" id="fs" role="dialog" aria-label="Part details"><div class="fsbar"><button id="fsx">&#8249; Back</button><b>Part</b><button id="fsx2" aria-label="Close">&#10005;</button></div><div class="fsin"></div></div>'
                + (f'<details class="map"><summary>Pieces that are not part of this set ({sum(len(v) for v in strays.values())})</summary><p style="font-size:13px;color:var(--mut)">'
                   f'No part in your parts list matches these. Some may be from another set; some are identification mistakes.</p>{rows_out}</details>' if strays else "")
                + (f'<details class="map"><summary>Count-only view: every piece Brickognize named, no set needed</summary><table class="inv"><tr><th>Part</th><th>ID</th><th>Found</th></tr>{rows_all}</table></details>' if allg else "")
                + "</section>")

    # ---- setup
    st_ = collections.Counter(p["status"] for p in mt["pieces"])
    rv = mt["settings"]
    ok_n = st_["matched"] + st_["checked"]
    mode = ("Brickognize (an outside service you turned on)" if mt["mode"] == "brickognize" else "local guesses, checked by Claude")
    if mt.get("stopped"):
        mode += f"; Brickognize stopped ({esc(mt['stopped'])}) and Claude checked the rest"
    setmap = S.save(Image.open(os.path.join(work, "table", "setup-map.jpg")), "setup-map.jpg", 1600)
    prows = "".join(f"<tr class='{'ok' if len(found.get(el, [])) >= need[el] else ('part' if found.get(el) else 'none')}'><td>{esc(el)}</td><td>{esc(part_name(el))}</td><td>{need[el]}</td><td>{len(found.get(el, []))}</td></tr>"
                    for el in sorted(parts, key=lambda e: (-need[e], e)))
    demo = f'<div class="card demo"><div style="padding:12px">{a.demo_note}</div></div>' if a.demo_note else ""
    setup_html = (f'<section class="pg" data-page="-2" hidden><h2>Setup <small>What the photo found</small></h2>{demo}'
                  f'<div class="card"><div style="padding:12px"><details class="map"><summary>Settings: min score {rv["min_score"]:.2f}, tie margin {rv["tie_margin"]:.2f}</summary>'
                  f'<p style="font-size:14px">Identified by: {mode}.</p><p style="font-size:14px">A piece goes to the Claude check when its score is under <b>{rv["min_score"]:.2f}</b>, its top two answers are within <b>{rv["tie_margin"]:.2f}</b>, '
                  f'or the top answer is not in your parts list. Step drawings go to the check when the best picture match beats the next by less than <b>{rv["drawing_gap"]:.2f}</b>.</p>'
                  f'<p style="font-size:13px;color:var(--mut)">These are settings in config.json. Photo quality and unusual pieces change what works: raise min score for blurry photos, glare or a busy table; lower it for sharp photos on a plain light background.</p></details>'
                  f'<p><b>{sum(v for k, v in st_.items() if k != "ignored")} pieces found</b> in the photo of the table.</p>'
                  f'<div class="stats"><span class="tag ok">{ok_n} identified and in the set</span><span class="tag maybe">{st_["low"]} unsure</span><span class="tag none">{st_["notinset"] + st_["noanswer"]} not in this set or not identified</span>'
                  + (f'<span class="tag none">{st_["big"]} not looked at yet</span>' if st_["big"] else "") +
                  f'</div><img src="{setmap}" data-zoom alt="The table, every piece ringed: green identified, amber unsure, red not in the set" style="width:100%;border-radius:10px;margin:10px 0">'
                  f'<p style="font-size:13px;color:var(--mut)">Green = identified and in the set. Amber = unsure. Red = not in this set or not identified. Tap to zoom.</p>'
                  f'<details class="map"><summary>Parts list: found vs needed ({len(found)} of {len(need)} kinds seen)</summary><table class="inv"><tr><th>Element</th><th>Part</th><th>Need</th><th>Found</th></tr>{prows}</table>'
                  f'<p style="font-size:12px;color:var(--mut)">"Found" counts pieces in the photo only. Pieces still in unopened bags are not counted.</p></details>'
                  f'<details class="map"><summary>Photo tips for better results</summary><ol style="font-size:14px;padding-left:20px;margin:6px 0">'
                  f'<li><b>Use a light, plain background.</b> Dark or patterned surfaces, like a wood table, hide dark pieces.</li>'
                  f'<li><b>Spread the pieces out</b> so none touch. Pieces that touch get counted as one.</li>'
                  f'<li><b>Avoid glare.</b> White pieces disappear into a shiny spot.</li>'
                  f'<li><b>One photo of the whole table from straight above</b>, with all four corners in it. Close-ups of parts of the table, taken right after without moving anything, sharpen small pieces.</li>'
                  f'<li><b>Retake the photo every few pages</b> as pieces get used.</li></ol></details></div></div></section>')

    pagenums = [SETUP, INVENTORY] + built
    RANGES = {str(SETUP): "Setup", str(INVENTORY): "Inventory", **{str(p): r for p, r in ranges.items()}}
    css = open(os.path.join(C.SKILL, "site", "guide.css")).read() + open(os.path.join(C.SKILL, "site", "extra.css")).read()
    js = (open(os.path.join(C.SKILL, "site", "guide.js")).read().replace("PREFIX_JSON", json.dumps(cfg["site"]["storage_prefix"]))
          .replace("PAGES_JSON", json.dumps(pagenums)).replace("RANGES", json.dumps(RANGES)))
    grid = ('<button data-p="-2"><b>Setup</b><span>start here</span></button><button data-p="-1"><b>Inventory</b><span>all parts</span></button>'
            + "".join(f'<button data-p="{p}"><b>p{p}</b><span>{esc(ranges[p])}</span></button>' for p in built))
    more = ("" if set(built) >= set(step_pages) else
            f'<p style="font-size:13px;color:var(--mut);margin:14px 0 0">{len(built)} of {len(step_pages)} pages with steps are in the guide. Ask Claude for the next ones.</p>')
    footer = (a.demo_note and '<p><b>A demo with a made-up set.</b> The set, its instructions and the table were invented and drawn by code.</p>') or (
        '<p><b>For your own use.</b> This guide shows pages of your instruction book, which belong to their publisher: do not publish it. '
        'Identification can be wrong; the book is always right.</p>')
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex"><link rel="icon" href="data:,"><meta name="theme-color" content="#ffffff"><title>{esc(title)} build guide</title><style>{css}</style></head><body>
<div class="top"><h1>{esc(title)} <span><span id="cnt"></span> <button id="snd" aria-label="Sound on or off">&#128266;</button></span></h1><div class="bar"><i></i></div></div>
<noscript><p style="padding:12px">This guide needs JavaScript.</p></noscript>
<main>{setup_html}{inv_html}{"".join(pages_html[p] for p in built)}
<details class="map"><summary>How to read this guide</summary><p style="font-size:14px;color:var(--mut)">Labels are step + letter: 5a is the first part in step 5's parts box, counting left to right, matching the big step numbers in the book. Under each part is its element ID from the parts list at the back of the book. Each part shows its drawing and a map of the table with every matching piece ringed: any of them will do. Tick a part when you have it and it folds away; tick "Done" and the step folds and the next one opens. Finish a page and the guide moves to the next one. Your phone remembers. Tap any picture to zoom.</p></details>
</main>
<footer>{footer}<p>Made with brick-build-guide-kit. Not affiliated with, sponsored or endorsed by any toy company. LEGO&reg; is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.</p>
<p><button class="reset">Clear all ticks</button></p></footer>
<nav class="nav"><button id="prev" aria-label="Previous page">&#8249; Prev</button><button class="pick"><span id="pl">Page</span> &#9662;</button><button id="next" aria-label="Next page">Next &#8250;</button></nav>
<div class="sheet"><div class="panel"><b>Go to page</b><p style="margin:4px 0 12px;font-size:13px;color:var(--mut)">Book page, with the steps on it. Green = every step done</p><div class="grid">{grid}</div>{more}</div></div>
<div class="zoom"><button class="zx" aria-label="Close">&#10005;</button><img alt=""></div>
<script>{js}</script></body></html>'''
    open(os.path.join(out, "index.html"), "w").write(page)
    C.jwrite(os.path.join(out, "state.json"), state)
    print(f"guide: {os.path.join(out, 'index.html')}  (pages {built or 'none yet'}; {len(parts)} parts, {ok_n} pieces identified)")


if __name__ == "__main__":
    main()
