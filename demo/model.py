"""The made-up demo set: the Pebble Rover, 24 pieces, 8 steps on book pages 3-7.

Every name and number here is invented for the demo. Element IDs start with D so
they cannot be mistaken for real ones.
"""

SET = {"name": "Pebble Rover", "number": "DEMO-01"}

# element: kind and size, colour, plain name
PARTS = {
    "D1001": dict(kind="plate", w=6, d=4, cname="Dark grey", hex="#5b6168", name="Plate 4 x 6"),
    "D1002": dict(kind="brick", w=2, d=1, cname="Yellow", hex="#f2c318", name="Brick 1 x 2"),
    "D1003": dict(kind="wheel", d=1, r=1.05, cname="Black", hex="#2b2d31", name="Wheel, small"),
    "D1004": dict(kind="brick", w=2, d=4, cname="Blue", hex="#2f6fc4", name="Brick 2 x 4"),
    "D1005": dict(kind="plate", w=2, d=4, cname="Blue", hex="#2f6fc4", name="Plate 2 x 4"),
    "D1006": dict(kind="slope", d=2, cname="Red", hex="#d1352b", name="Slope 45 2 x 2"),
    "D1007": dict(kind="plate", w=1, d=4, cname="White", hex="#f4f4f1", name="Plate 1 x 4"),
    "D1008": dict(kind="brick", w=1, d=1, cname="Red", hex="#d1352b", name="Brick 1 x 1"),
    "D1009": dict(kind="tile", w=2, d=1, cname="Light grey", hex="#a7acb2", name="Tile 1 x 2"),
    "D1010": dict(kind="plate", w=2, d=2, cname="Green", hex="#3a9a4a", name="Plate 2 x 2"),
    "D1011": dict(kind="round", h=1.2, cname="White", hex="#f4f4f1", name="Round brick 1 x 1"),
    "D1012": dict(kind="round", h=0.4, cname="Orange", hex="#f08a24", name="Round plate 1 x 1"),
}

Z0 = 0.4            # top of the base plate
ZB = Z0 + 1.2       # top of the first brick layer

# Each step: (page, step, [(element, x, y, z)])
STEPS = [
    (3, 1, [("D1001", 0, 0, 0), ("D1002", 0, 0, Z0), ("D1002", 4, 0, Z0), ("D1002", 0, 3, Z0), ("D1002", 4, 3, Z0)]),
    (4, 2, [("D1003", 1, -1, .5), ("D1003", 5, -1, .5), ("D1003", 1, 4, .5), ("D1003", 5, 4, .5)]),
    (5, 3, [("D1004", 2, 0, Z0)]),
    (5, 4, [("D1005", 0, 0, ZB), ("D1005", 4, 0, ZB)]),
    (6, 5, [("D1006", 4, 0, ZB + .4), ("D1006", 4, 2, ZB + .4), ("D1007", 2, 0, ZB), ("D1007", 3, 0, ZB)]),
    (6, 6, [("D1008", 0, 0, ZB + .4), ("D1008", 0, 3, ZB + .4)]),
    (7, 7, [("D1009", 2, 1, ZB + .4), ("D1009", 2, 2, ZB + .4), ("D1010", 0, 1, ZB + .4)]),
    (7, 8, [("D1011", 3, 3, ZB + .4), ("D1012", 0, 0, ZB + 1.6), ("D1012", 0, 3, ZB + 1.6)]),
]
BAGS = {3: 1, 5: 2}          # page a bag starts on -> bag number

# The demo table: every part except these, still in a bag, plus three strays from another set.
MISSING = {"D1003": 1, "D1012": 2}
STRAYS = [dict(kind="brick", w=3, d=1, hex="#e86fae", name="Brick 1 x 3", cname="Pink"),
          dict(kind="round", h=1.2, hex="#9ccc3c", name="Round brick 1 x 1", cname="Lime"),
          dict(kind="plate", w=2, d=2, hex="#7b52b3", name="Plate 2 x 2", cname="Purple")]
