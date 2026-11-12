"""Common LEGO colors: name, LDraw color code, RGB (0..1 linear-ish sRGB).

Used for automatic material -> LEGO color matching (nearest RGB) and for
LDraw export. Extend freely; keep names matching BrickLink/LEGO naming.
"""

LEGO_COLORS = [
    ("White",              15,  (0.95, 0.95, 0.95)),
    ("Black",               0,  (0.05, 0.06, 0.08)),
    ("Bright Red",          4,  (0.79, 0.10, 0.04)),
    ("Bright Blue",         1,  (0.00, 0.33, 0.75)),
    ("Bright Yellow",      14,  (0.95, 0.80, 0.22)),
    ("Bright Green",        2,  (0.00, 0.52, 0.17)),
    ("Dark Green",         10,  (0.14, 0.47, 0.25)),
    ("Bright Orange",      25,  (1.00, 0.54, 0.09)),
    ("Medium Lilac",       26,  (0.51, 0.00, 0.48)),
    ("Bright Purple",      28,  (0.85, 0.25, 0.70)),
    ("Dark Pink",          94,  (0.85, 0.42, 0.65)),
    ("Reddish Brown",      70,  (0.35, 0.16, 0.07)),
    ("Brown",               6,  (0.35, 0.22, 0.15)),
    ("Tan",                19,  (0.89, 0.80, 0.62)),
    ("Light Bluish Gray",  71,  (0.63, 0.65, 0.66)),
    ("Dark Bluish Gray",   72,  (0.42, 0.43, 0.41)),
    ("Medium Stone Gray", 272,  (0.70, 0.70, 0.70)),
    ("Dark Stone Gray",    72,  (0.42, 0.43, 0.41)),
    ("Sand Green",         80,  (0.63, 0.74, 0.67)),
    ("Sand Blue",          79,  (0.40, 0.48, 0.60)),
    ("Medium Azure",      322,  (0.21, 0.68, 0.75)),
    ("Dark Azure",        323,  (0.03, 0.55, 0.79)),
    ("Medium Nougat",     319,  (0.85, 0.60, 0.45)),
    ("Light Nougat",       84,  (0.92, 0.76, 0.60)),
    ("Dark Turquoise",    321,  (0.00, 0.50, 0.50)),
    ("Lime",               34,  (0.70, 0.86, 0.00)),
    ("Trans-Clear",        47,  (0.90, 0.95, 0.95)),
    ("Trans-Red",          36,  (0.85, 0.20, 0.20)),
    ("Trans-Light Blue",   43,  (0.70, 0.85, 0.90)),
    ("Gold",              297,  (0.85, 0.65, 0.25)),
    ("Silver",            315,  (0.75, 0.76, 0.78)),
]

LEGO_COLOR_NAMES = [c[0] for c in LEGO_COLORS]
LDRAW_CODE = {c[0]: c[1] for c in LEGO_COLORS}
