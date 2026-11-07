---
name: brick-build-guide
description: Turn a building-instruction PDF the user provides, plus an overhead photo of their loose pieces spread on a table, into a phone build guide - each book page with its new parts labelled step + letter, an inventory of every part, and a map of where each matching piece is on the table. Use when someone has a mixed-up pile of building bricks and their instruction PDF and wants help finding the pieces for each step, wants to know which pieces are on the table or missing, or asks for the next pages of a guide already started.
---

# Brick build guide

Turns **the user's own instruction PDF** and **a photo of their pieces on a table** into a
static web page they can follow on a phone: Setup, Inventory, and the book pages built so
far, a couple at a time. Scripts do the bulk of the work; you check only what they are
unsure of, by eye.

## Ground rules

- **The user supplies the PDF.** Ask them to upload or point you to it. Never explain how
  to find, search for or download instructions, and never fetch them yourself.
- **Brand care.** The guide shows pages of the user's book, which belong to their publisher.
  It is for their own use: never publish it, upload it or put it in a repository. Do not
  call the guide or anything you make "official". The kit is not affiliated with any toy company.
- **Brickognize is OFF unless the user opts in.** Before turning it on, tell them, in these
  words or close: *"Brickognize (brickognize.com) is a free outside service that names
  bricks from a picture. If you turn it on, crops of single pieces from your photo, and
  single-part drawings from your PDF (its parts list, and step drawings I am unsure of), are
  sent to it. Its terms let it keep uploaded pictures, including to
  train its models. Without it I look at the pieces myself, which is slower but sends
  nothing anywhere. Turn it on?"* Set `"brickognize": {"enabled": true}` in `WORK/config.json`
  only on a clear yes. `scripts/identify.py` is the only code that uses the network.
- **Never send anything to Brickognize yourself** (no curl, no other script). If it fails,
  refuses or asks for payment, identify.py stops and you do the check instead.
- **The book is right; identification can be wrong.** Say so when it matters.

## Setup (once)

Scripts are in `scripts/` next to this file; call that folder `SCRIPTS`. Pick a work folder
(default `./brick-guide-work`, called `WORK`). Everything goes there.

```bash
command -v pdftoppm pdftotext || echo "install poppler: apt install poppler-utils / brew install poppler"
python3 -m venv WORK/.venv && WORK/.venv/bin/pip install -q -r SCRIPTS/../requirements.txt
PY=WORK/.venv/bin/python
```

## 1. The book

```bash
$PY SCRIPTS/book.py --work WORK --pdf path/to/instructions.pdf
```

Then look at the sheets it wrote and record answers in `WORK/review/review.json`
(format in `scripts/match.py`'s docstring; create it if missing):

- `review/book-pages-*.jpg`: find the pages where a **numbered bag** starts (a bag picture
  with a number) and write `"bags": {"<page>": <bag number>}`. If the book has no numbered
  bags, leave it out.
- If Brickognize is off, `review/book-parts-*.jpg` shows every part with its element ID:
  write `"names": {"<element>": "<Colour> <plain name>"}` (e.g. "Black plate 1 x 2").
  Short and plain; the element ID is shown beside it anyway.

Set `"site": {"title": ...}` in config.json to the set's name if the user tells you it.

## 2. The table

Photo advice to pass on before they shoot: a light, plain surface; pieces spread so none
touch; no glare; one photo of the whole table from straight above with all four corners in it.

```bash
$PY SCRIPTS/table.py  --work WORK --photo path/to/table.jpg
$PY SCRIPTS/pieces.py --work WORK [--closeups part1.jpg part2.jpg ...]
$PY SCRIPTS/identify.py --work WORK
$PY SCRIPTS/match.py  --work WORK
```

- After table.py, look at `table/check.jpg`. If the outline misses the tabletop, give the user
  `WORK/fixcrop/index.html` to open in a browser: they drag four dots to the corners and
  press Done, which prints corners to paste back. Then run `table.py --work WORK --corners '<that text>'`
  and carry on.
- **Close-ups** are optional: photos of parts of the table from closer, taken at the same
  time as the overhead one, with no pieces moved in between. Pieces a close-up covers get
  sharper crops. A close-up that does not line up with the overhead photo is skipped and
  reported; tell the user it was probably taken after pieces moved.
- Identify **every** piece now, once. Later pages reuse it.

## 3. The Claude check (only what the scripts are unsure of)

match.py prints how many pieces need you and writes `review/table-*.jpg`. Each tile shows the
piece as photographed, then the parts-list drawings of its best candidates; the caption has
the piece number, its status and the candidates' element IDs.

1. For each tile, write an answer under `"pieces"` in review.json: the element ID, or
   `"not-in-set"`, or `"not-a-piece"` (a scratch, a shadow, the table edge), or
   `{"element": ..., "count": 2}` for touching identical pieces. If the candidates are all
   wrong, find the part on `review/book-parts-*.jpg`. Skip a tile you cannot decide.
2. **Big pieces and clusters.** Pieces marked `big` are blobs the scripts could not
   separate: big plates touching, glare, or several small pieces touching. Look at
   `table/pieces-map.jpg` and `table/grid.jpg` (grid lines every 200 px, labelled). Mark the
   blob `"not-a-piece"` and add each piece in it by position:
   `"add": [{"at": [x, y], "r": <radius px>, "element": "..."}]`. When you cannot name a
   piece, leave out `"element"`: identify.py crops that spot and names it like any other
   piece (rerun identify.py, then match.py), and any unsure result comes back to the sheets.
3. **One look for misses.** Rerun match.py, then look over `table/setup-map.jpg` once
   (green = identified, amber = unsure, red = not in the set, purple = not looked at yet).
   Add anything missed with `"add"`.
4. Rerun `match.py`. Repeat only if something new appeared in the queue.

Decisions of when to check are settings in config.json (`review.min_score`, default 0.60;
`review.tie_margin`). Blurry photos, glare or unusual pieces call for a higher min_score;
sharp photos on a plain light background can take a lower one. Change them only if the user
asks or the results clearly call for it, and say what you changed.

## 4. Pages, a couple at a time

Ask which pages the user is on (or start at the first page with steps). For pages A to B:

```bash
$PY SCRIPTS/match.py --work WORK --check-pages A-B
```

Look at `review/drawings-A-B-*.jpg` (each tile: the drawing from the step's parts box, then
the parts-list candidates) and write `"drawings": {"<id>": "<element>"}` for any that are
wrong. Then:

```bash
$PY SCRIPTS/match.py --work WORK
$PY SCRIPTS/site.py  --work WORK --pages A-B
```

The guide is `WORK/site/index.html`. To open it on a phone on the same home network:
`cd WORK/site && python3 -m http.server 8000` and browse to the computer's address, port
8000. Keep it on the home network; it is not for publishing.

Tell the user, briefly: which pages are in the guide, how many pieces were found and
identified, and anything not found ("not found in your photo: check bag 3").

## 5. Next pages, and new photos

- **Next pages:** repeat step 4. site.py keeps the pages built before.
- **A new photo** (every few pages, since pieces get used): run table.py with `--photo`,
  then pieces.py, identify.py, match.py. Pieces that have not moved keep their earlier
  identification (and are not sent again); only moved or new ones need the check.
  Then rebuild with `site.py --work WORK` (no `--pages` needed).
- **"Revise step 7":** fix the answer in review.json, rerun match.py and site.py.

## Labels

Each part is labelled **step + letter**, left to right in that step's parts box (5a, 5b, ...),
so it matches the big step numbers in the book, with its element ID from the parts list
under it. The bag number comes from the book's numbered bags.

## If something fails

- `book.py` needs a PDF with a text layer and a parts list (count labels like "4x" with an
  element ID under each). A scanned PDF will not work; say so.
- If the corner finder fails it uses the whole photo: use the crop fixer.
- If Brickognize stops (see `brickognize/sent.log`), carry on without it; everything it
  did not answer goes to your check.
