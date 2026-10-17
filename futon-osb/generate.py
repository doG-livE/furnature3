#!/usr/bin/env python3
"""Flat-pack OSB bifold futon chair: generates part geometry, sheet nesting,
DXF/SVG cut files and preview images.  Units: inches.

Re-run after measuring your OSB:  python3 generate.py --thickness 0.70
Needs: shapely, ezdxf, matplotlib.
"""
import argparse, csv, math, os
from shapely.geometry import box, Point, Polygon, MultiPolygon
from shapely.geometry.polygon import orient
from shapely import affinity
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument("--thickness", type=float, default=0.719, help="measured OSB thickness (23/32 nominal)")
ap.add_argument("--clearance", type=float, default=0.04, help="slot width = thickness + clearance")
ap.add_argument("--bit", type=float, default=0.25, help="end mill diameter (dogbone size)")
ap.add_argument("--width", type=float, default=32.0, help="chair width (deck size across the seat)")
ap.add_argument("--deck-top", type=float, default=11.0, help="deck top height; + 6in cushion = seat height")
ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
A = ap.parse_args()

T = A.thickness
S = T + A.clearance            # slot / mortise width
R = A.bit / 2 + 0.005           # dogbone radius
W = A.width
RIB_TOP = A.deck_top - T
SEAT_D, GAP, BACK_D = 25.0, 4.5, 25.0     # from the KD sheet: 25 + 4.5 + 25 = 54.5 bed depth
BACK_X0 = SEAT_D + GAP
RIB_X0, RIB_X1 = 0.5, SEAT_D + GAP + BACK_D - 0.5
RIB_Y = [1.75, W / 2, W - 1.75]           # rib centrelines across the width
TAB_H = T - 0.06                          # tabs sit just below deck top
TABS_LOCAL = [(3.0, 6.0), (19.0, 22.0)]   # tab x-ranges, measured from each deck's front edge
ARCH_TOP, ARCH_R = 5.0, 1.5
FRONT_LEG, MID_LEG, REAR_LEG = (RIB_X0, 5.5), (23.5, 31.5), (49.0, RIB_X1)
STRETCH_X = [3.0, 51.5]                   # front / rear stretcher planes
STRETCH_H = 5.0
PANEL_X = BACK_X0                         # removable back-support panel plane
HEEL = (SEAT_D + 0.2, SEAT_D + 2.2, 0.75) # notch that catches the back deck's bottom edge
BACK_ANGLE = math.radians(60)             # back recline, from horizontal
LEN_Y0, LEN_Y1 = 0.5, W - 0.5             # stretcher/panel extent across the width

# back geometry in sofa mode: back deck's bottom edge sits in the heel notch
z_notch = RIB_TOP - HEEL[2]
x_rear_foot = HEEL[0] + T * math.sin(BACK_ANGLE)
def back_rear_face_z(x): return z_notch + (x - x_rear_foot) * math.tan(BACK_ANGLE)
PANEL_TOP = back_rear_face_z(PANEL_X - T / 2)
SOFA_TOP = z_notch + T * math.cos(BACK_ANGLE) + BACK_D * math.sin(BACK_ANGLE)

def dogbone(poly):
    """Cut a tool-radius relief into every ~90 deg inside corner of the material."""
    poly = orient(poly, 1.0)
    cuts = []
    for ring in [poly.exterior] + list(poly.interiors):
        pts = list(ring.coords)[:-1]
        n = len(pts)
        for i in range(n):
            p, v, q = pts[i - 1], pts[i], pts[(i + 1) % n]
            d1 = (v[0] - p[0], v[1] - p[1]); d2 = (q[0] - v[0], q[1] - v[1])
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            if l1 < 1e-9 or l2 < 1e-9: continue
            d1 = (d1[0] / l1, d1[1] / l1); d2 = (d2[0] / l2, d2[1] / l2)
            cross = d1[0] * d2[1] - d1[1] * d2[0]
            dot = d1[0] * d2[0] + d1[1] * d2[1]
            if cross < -0.9 and abs(dot) < 0.1:      # right turn of ~90 deg = inside corner
                bx, by = d2[0] - d1[0], d2[1] - d1[1]
                bl = math.hypot(bx, by)
                cuts.append(Point(v[0] + R * bx / bl, v[1] + R * by / bl).buffer(R, 32))
    return poly.difference(unary_union(cuts)) if cuts else poly

def rounded_box(x0, y0, x1, y1, r):
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, 32)

def stadium(cx, cy, length, width):   # slot long in y
    h = (length - width) / 2
    return box(cx, cy - h, cx, cy + h).buffer(width / 2, 32) if h > 0 else Point(cx, cy).buffer(width / 2, 32)

# ---------------- parts (each in its own 2D frame) ----------------
def rib():  # frame: x = front-to-back, y = height
    p = box(RIB_X0, 0, RIB_X1, RIB_TOP)
    for x0 in (0.0, BACK_X0):
        for a, b in TABS_LOCAL:
            p = p.union(box(x0 + a, RIB_TOP - 0.01, x0 + b, RIB_TOP + TAB_H))
    p = p.difference(box(HEEL[0], z_notch, HEEL[1], RIB_TOP + 1))
    p = p.difference(box(PANEL_X - S / 2, RIB_TOP / 2, PANEL_X + S / 2, RIB_TOP + 1))
    for sx in STRETCH_X:
        p = p.difference(box(sx - S / 2, -1, sx + S / 2, STRETCH_H / 2))
    p = dogbone(p)
    for a, b in ((FRONT_LEG[1], MID_LEG[0]), (MID_LEG[1], REAR_LEG[0])):
        p = p.difference(rounded_box(a, -10, b, ARCH_TOP, ARCH_R))
    return p

def deck():  # frame: x = front-to-back (0..25), y = across the width (0..W)
    p = box(0, 0, SEAT_D, W)
    for ry in RIB_Y:
        for a, b in TABS_LOCAL:
            p = p.difference(box(a - 0.03, ry - S / 2, b + 0.03, ry + S / 2))
    p = dogbone(p)
    vents = []
    for y0, y1 in zip(RIB_Y[:-1], RIB_Y[1:]):
        cy, L = (y0 + y1) / 2, (y1 - y0) - 4.5
        for cx in (4.5, 8.5, 12.5, 16.5, 20.5):
            vents.append(stadium(cx, cy, L, 1.0))
    return p.difference(unary_union(vents))

def slotted_bar(height, slot_from_top, slot_depth):  # frame: x = across width, y = height
    p = box(LEN_Y0, 0, LEN_Y1, height)
    for ry in RIB_Y:
        y0, y1 = (height - slot_depth, height + 1) if slot_from_top else (-1, slot_depth)
        p = p.difference(box(ry - S / 2, y0, ry + S / 2, y1))
    p = dogbone(p)
    for a, b in zip(RIB_Y[:-1], RIB_Y[1:]):          # floor relief so it rocks less on uneven floors
        p = p.difference(rounded_box(a + 2.0, -10, b - 2.0, 0.4, 0.3))
    return p

def stretcher(): return slotted_bar(STRETCH_H, True, STRETCH_H / 2)

def panel():
    p = slotted_bar(PANEL_TOP, False, RIB_TOP / 2)
    for cx in (W * 0.3, W * 0.7):                     # finger pulls for lifting it out
        p = p.difference(affinity.rotate(stadium(cx, PANEL_TOP - 2.0, 4.0, 1.25), 90, origin=(cx, PANEL_TOP - 2.0)))
    return p

PARTS = [  # name, qty, factory, note
    ("rib", len(RIB_Y), rib, "legs + deck supports; tabs up"),
    ("deck", 2, deck, "seat deck and back deck are identical"),
    ("stretcher", 2, stretcher, "front and rear, slots up"),
    ("back-support", 1, panel, "sofa mode only; drops into the rib slots behind the seat"),
]
GEOM = {name: f() for name, q, f, n in PARTS}

# ---------------- nesting on 96 x 48 sheets ----------------
SHEET_L, SHEET_W, M, G = 96.0, 48.0, 0.75, 0.75
def place(g, x, y, rot=0):
    if rot: g = affinity.rotate(g, rot, origin=(0, 0))
    b = g.bounds
    return affinity.translate(g, x - b[0], y - b[1])
def h(g, rot=0):
    b = (affinity.rotate(g, rot, origin=(0, 0)) if rot else g).bounds
    return b[3] - b[1], b[2] - b[0]

rib_h, rib_w = h(GEOM["rib"])
st_h, st_w = h(GEOM["stretcher"])
pn_h, pn_w = h(GEOM["back-support"])
dk_h, dk_w = h(GEOM["deck"], 90)   # rotate so the 32in span runs along the sheet's strong 8ft axis
sheets = [[], []]
y = M
for i in range(len(RIB_Y)):
    sheets[0].append((f"rib {i+1}", place(GEOM["rib"], M, y))); y += rib_h + G
for i in range(2):
    sheets[0].append((f"stretcher {i+1}", place(GEOM["stretcher"], M, y))); y += st_h + G
x2 = M + rib_w + G
sheets[0].append(("back-support", place(GEOM["back-support"], x2, M)))
sheets[0].append(("deck A (seat)", place(GEOM["deck"], x2, M + pn_h + G, 90)))
sheets[1].append(("deck B (back)", place(GEOM["deck"], M, M, 90)))
for s in sheets:
    for name, g in s:
        b = g.bounds
        assert b[0] >= M - 1e-6 and b[1] >= M - 1e-6 and b[2] <= SHEET_L - M + 1e-6 and b[3] <= SHEET_W - M + 1e-6, (name, b)
    for i in range(len(s)):
        for j in range(i + 1, len(s)):
            assert s[i][1].distance(s[j][1]) >= G - 1e-6, (s[i][0], s[j][0])

# ---------------- writers ----------------
import ezdxf
def rings(g):
    for poly in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        yield "CUT_OUTSIDE", list(poly.exterior.coords)
        for r in poly.interiors: yield "CUT_INSIDE", list(r.coords)

def write_dxf(path, items, sheet=False):
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 1; doc.header["$MEASUREMENT"] = 0
    doc.layers.add("CUT_OUTSIDE", color=1); doc.layers.add("CUT_INSIDE", color=5); doc.layers.add("SHEET_REF_DO_NOT_CUT", color=8)
    msp = doc.modelspace()
    if sheet:
        msp.add_lwpolyline([(0, 0), (SHEET_L, 0), (SHEET_L, SHEET_W), (0, SHEET_W)], close=True, dxfattribs={"layer": "SHEET_REF_DO_NOT_CUT"})
    for _, g in items:
        for layer, pts in rings(g):
            msp.add_lwpolyline([(round(a, 4), round(b, 4)) for a, b in pts[:-1]], close=True, dxfattribs={"layer": layer})
    doc.saveas(path)

def write_svg(path, items, w, hgt, labels=True):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}in" height="{hgt}in" viewBox="0 0 {w} {hgt}">',
           f'<rect x="0" y="0" width="{w}" height="{hgt}" fill="none" stroke="#999" stroke-width="0.05"/>']
    for name, g in items:
        d = ""
        for layer, pts in rings(g):
            d += "M" + " L".join(f"{a:.4f},{hgt-b:.4f}" for a, b in pts[:-1]) + " Z "
        out.append(f'<path d="{d}" fill="#e8c98f" fill-rule="evenodd" stroke="#000" stroke-width="0.03"/>')
        if labels:
            c = g.representative_point()
            out.append(f'<text x="{c.x:.2f}" y="{hgt-c.y:.2f}" font-size="1.4" font-family="sans-serif" fill="#a00">{name}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))

os.makedirs(os.path.join(A.out, "cut"), exist_ok=True)
os.makedirs(os.path.join(A.out, "parts"), exist_ok=True)
for i, s in enumerate(sheets, 1):
    write_dxf(os.path.join(A.out, "cut", f"sheet-{i}.dxf"), s, sheet=True)
    write_svg(os.path.join(A.out, "cut", f"sheet-{i}.svg"), s, SHEET_L, SHEET_W, labels=False)
for name, q, f, n in PARTS:
    g = place(GEOM[name], 0, 0)
    b = g.bounds
    write_dxf(os.path.join(A.out, "parts", f"{name}.dxf"), [(name, g)])
    write_svg(os.path.join(A.out, "parts", f"{name}.svg"), [(name, g)], math.ceil(b[2]), math.ceil(b[3]), labels=False)

with open(os.path.join(A.out, "parts-list.csv"), "w", newline="") as fh:
    wr = csv.writer(fh); wr.writerow(["part", "qty", "length_in", "height_in", "notes"])
    for name, q, f, n in PARTS:
        b = GEOM[name].bounds
        L, H = sorted([b[2] - b[0], b[3] - b[1]], reverse=True)
        wr.writerow([name, q, f"{L:.2f}", f"{H:.2f}", n])

# ---------------- previews ----------------
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
def draw(ax, g, fc="#e8c98f", ec="k", lw=0.6):
    for poly in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        ax.add_patch(MPoly(list(poly.exterior.coords), fc=fc, ec=ec, lw=lw))
        for r in poly.interiors: ax.add_patch(MPoly(list(r.coords), fc="white", ec=ec, lw=lw))

fig, axs = plt.subplots(len(sheets), 1, figsize=(12, 6.3 * len(sheets)))
for i, (ax, s) in enumerate(zip(axs, sheets), 1):
    ax.add_patch(MPoly([(0, 0), (SHEET_L, 0), (SHEET_L, SHEET_W), (0, SHEET_W)], fc="#f6f6f6", ec="#888"))
    for name, g in s:
        draw(ax, g); c = g.representative_point(); ax.text(c.x, c.y, name, fontsize=9, color="#a00")
    ax.set_xlim(-1, SHEET_L + 1); ax.set_ylim(-1, SHEET_W + 1); ax.set_aspect("equal")
    ax.set_title(f"Sheet {i} of {len(sheets)}  (4x8, 23/32 OSB, strong axis left-right)")
fig.tight_layout(); fig.savefig(os.path.join(A.out, "nesting.png"), dpi=110); plt.close(fig)

def side_view(ax, sofa):
    draw(ax, GEOM["rib"])
    for sx in STRETCH_X: ax.add_patch(MPoly(list(box(sx - T/2, 0, sx + T/2, STRETCH_H).exterior.coords), fc="#c9a46a", ec="k", lw=0.6))
    seat = box(0, RIB_TOP, SEAT_D, RIB_TOP + T); draw(ax, seat, fc="#d9b06e")
    ax.add_patch(MPoly(list(box(0, A.deck_top, SEAT_D, A.deck_top + 6).exterior.coords), fc="#9fc3e8", ec="#467", lw=0.5, alpha=0.6))
    if sofa:
        ax.add_patch(MPoly(list(box(PANEL_X - T/2, 0, PANEL_X + T/2, PANEL_TOP).exterior.coords), fc="#b5651d", ec="k", lw=0.6))
        b = affinity.rotate(box(0, 0, BACK_D, T), math.degrees(BACK_ANGLE), origin=(0, 0))
        b = affinity.translate(b, x_rear_foot, z_notch)    # rear-bottom corner on the notch floor
        draw(ax, b, fc="#d9b06e")
        xf, zf = HEEL[0], z_notch + T * math.cos(BACK_ANGLE)   # front-bottom corner of the back deck
        s0 = (A.deck_top + 6 - zf) / math.sin(BACK_ANGLE)
        cush = affinity.rotate(box(0, 0, BACK_D - s0 + 4, 6), math.degrees(BACK_ANGLE), origin=(0, 0))
        cush = affinity.translate(cush, xf + s0 * math.cos(BACK_ANGLE), zf + s0 * math.sin(BACK_ANGLE))
        ax.add_patch(MPoly(list(cush.exterior.coords), fc="#9fc3e8", ec="#467", lw=0.5, alpha=0.6))
        ax.set_title(f'Chair mode: seat {A.deck_top + 6:.0f}" with 6" cushion, back deck top {SOFA_TOP:.1f}"')
    else:
        draw(ax, box(BACK_X0, RIB_TOP, BACK_X0 + BACK_D, RIB_TOP + T), fc="#d9b06e")
        ax.add_patch(MPoly(list(box(BACK_X0, A.deck_top, BACK_X0 + BACK_D, A.deck_top + 6).exterior.coords), fc="#9fc3e8", ec="#467", lw=0.5, alpha=0.6))
        ax.set_title(f'Lounger/bed mode: flat {SEAT_D + GAP + BACK_D}" deep, deck top {A.deck_top:.0f}"')
    ax.set_xlim(-2, 58); ax.set_ylim(-1, 38); ax.set_aspect("equal"); ax.grid(alpha=0.3)
fig, axs = plt.subplots(1, 2, figsize=(14, 5))
side_view(axs[0], True); side_view(axs[1], False)
fig.tight_layout(); fig.savefig(os.path.join(A.out, "side-views.png"), dpi=110); plt.close(fig)

print(f"T={T} slot={S:.3f} rib_top={RIB_TOP:.3f} panel_top={PANEL_TOP:.2f} back_top={SOFA_TOP:.2f}")
for i, s in enumerate(sheets, 1):
    area = sum(g.area for _, g in s); print(f"sheet {i}: {len(s)} parts, {100*area/(SHEET_L*SHEET_W):.0f}% used")
for name, q, f, n in PARTS:
    b = GEOM[name].bounds; print(name, q, f"{b[2]-b[0]:.2f} x {b[3]-b[1]:.2f}", GEOM[name].geom_type)
