#!/usr/bin/env python3
"""OSB version of the KD Frames Studio Bifold: a seat frame and an adjustable
back frame, each an egg-crate of on-edge OSB rails and slats, joined by a
pivot bolt, with a fold-down prop that seats in notches under the back rails.
Units: inches.  Run:  python3 generate.py --thickness 0.705
Needs: shapely, ezdxf, matplotlib.
"""
import argparse, csv, math, os
from shapely.geometry import box, Point, MultiPolygon, LineString
from shapely.geometry.polygon import orient
from shapely import affinity
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument("--thickness", type=float, default=0.719, help="measured OSB thickness (23/32 nominal)")
ap.add_argument("--clearance", type=float, default=0.04, help="slot width = thickness + clearance")
ap.add_argument("--bit", type=float, default=0.25, help="end mill diameter (dogbone size)")
ap.add_argument("--width", type=float, default=32.0, help="side-to-side length: 32 chair, 74 full, 78 queen")
ap.add_argument("--deck-top", type=float, default=11.0, help="deck top height (KD sheet uses 10)")
ap.add_argument("--angles", default="50,57,64", help="back recline settings, degrees from flat")
ap.add_argument("--bolt", type=float, default=0.406, help="pivot hole diameter (13/32 for 3/8 bolts)")
ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
A = ap.parse_args()

T, W, TOP = A.thickness, A.width, A.deck_top
S = T + A.clearance
R = A.bit / 2 + 0.005
ANGLES = [float(a) for a in A.angles.split(",")]

# --- layout from the KD sheet: 25" seat + 4.5" centre gap + 25" back = 54.5" flat
SEAT_D, GAP, BACK_D = 25.0, 4.5, 25.0
BACK_X0 = SEAT_D + GAP
SLAT_H, SLAT_N = 3.5, 7
SLAT_U = [1.0 + k * (SEAT_D - 2.0) / (SLAT_N - 1) for k in range(SLAT_N)]   # slat centres from each deck's front
LAP = SLAT_H / 2                                                            # cross-lap depth
BACK_RAIL_H = 4.0                  # back rails hang 0.5" below the slats so the prop can reach them
P = (27.0, TOP - 2.0)              # seat/back pivot bolt, in the centre gap
Q = (47.5, TOP - 5.0)              # prop pivot bolt, on the seat frame's rear arm
ARM_TOP, ARM_BOT = TOP - SLAT_H, TOP - 6.5   # rear arm carries the back deck when flat
PROP_W, TIP_IN = 2.0, 0.6          # prop width; how far the prop tip sits up inside the back rail

# --- planes across the width (y).  Seat rails outermost, back rails just inside them.
SEAT_PLANES = [0.5 + T / 2, W - 0.5 - T / 2]
BACK_PLANES = [0.5 + 1.5 * T, W - 0.5 - 1.5 * T]
CENTER = W > 48                    # a full/queen needs a centre rail in each deck
if CENTER:
    SEAT_PLANES.insert(1, W / 2); BACK_PLANES.insert(1, W / 2 + T)

def dogbone(poly):
    """Tool-radius relief in every ~90 deg inside corner of the material."""
    poly = orient(poly, 1.0); cuts = []
    for ring in [poly.exterior] + list(poly.interiors):
        pts = list(ring.coords)[:-1]; n = len(pts)
        for i in range(n):
            p, v, q = pts[i - 1], pts[i], pts[(i + 1) % n]
            d1 = (v[0] - p[0], v[1] - p[1]); d2 = (q[0] - v[0], q[1] - v[1])
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            if l1 < 1e-9 or l2 < 1e-9: continue
            d1 = (d1[0] / l1, d1[1] / l1); d2 = (d2[0] / l2, d2[1] / l2)
            if d1[0] * d2[1] - d1[1] * d2[0] < -0.9 and abs(d1[0] * d2[0] + d1[1] * d2[1]) < 0.1:
                bx, by = d2[0] - d1[0], d2[1] - d1[1]; bl = math.hypot(bx, by)
                cuts.append(Point(v[0] + R * bx / bl, v[1] + R * by / bl).buffer(R, 32))
    return poly.difference(unary_union(cuts)) if cuts else poly

def rbox(x0, y0, x1, y1, r): return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, 32)
def hole(c, d=None): return Point(c).buffer((d or A.bolt) / 2, 32)

# ---------------- back geometry (side view, x = front-to-back, z = up) ----------------
def back_pose(theta_deg):
    """Map back-rail coords (bed position) to world coords at recline angle theta."""
    return lambda g: affinity.rotate(g, theta_deg, origin=P)

def solve_notches(Lp):
    """For each recline angle find where the prop tip lands on the back rail (bed coords)."""
    out = []
    for th in ANGLES:
        t = math.radians(th)
        # tip centre in bed coords: (x, TOP - BACK_RAIL_H + TIP_IN); rotate about P; distance to Q == Lp
        zb = TOP - BACK_RAIL_H + TIP_IN - P[1]
        lo, hi = BACK_X0 + 2, BACK_X0 + BACK_D - 2
        def f(x):
            rx, rz = x - P[0], zb
            wx = P[0] + rx * math.cos(t) - rz * math.sin(t); wz = P[1] + rx * math.sin(t) + rz * math.cos(t)
            return math.hypot(wx - Q[0], wz - Q[1]) - Lp
        if f(lo) * f(hi) > 0: raise SystemExit(f"prop length {Lp} cannot reach angle {th}")
        for _ in range(60):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if f(lo) * f(m) > 0 else (lo, m)
        out.append((th, (lo + hi) / 2, TOP - BACK_RAIL_H + TIP_IN))
    return out

def prop_world(tip):           # stadium from Q to tip, in world coords
    return LineString([Q, tip]).buffer(PROP_W / 2, 32)

def tip_world(th, x, z):
    return affinity.rotate(Point(x, z), th, origin=P).coords[0]

# pick the prop length that keeps all notches on the rail and clear of the slats
best = None
for Lp10 in range(120, 220):
    Lp = Lp10 / 10
    try: sol = solve_notches(Lp)
    except SystemExit: continue
    xs = [x - BACK_X0 for _, x, _ in sol]
    clear = min(min(abs(x - u) for u in SLAT_U) for x in xs)
    spread = min(abs(a - b) for i, a in enumerate(xs) for b in xs[i + 1:]) if len(xs) > 1 else 9
    if xs and min(xs) > 6 and max(xs) < BACK_D - 2 and clear > 1.45 and spread > 2.6:
        best = (Lp, sol); break
if not best: raise SystemExit("no prop length fits; try other --angles")
PROP_L, NOTCHES = best
FOLDED_TIP = (Q[0] - PROP_L, Q[1])

# ---------------- parts ----------------
def seat_rail():   # seat frame side: seat beam, front leg, centre leg with pivot ear, rear arm + rear leg
    p = unary_union([
        box(0.5, TOP - 6.0, SEAT_D, TOP),                 # seat beam
        box(0.5, 0, 4.5, TOP),                            # front leg
        box(21.0, 0, 28.5, TOP - 6.0),                    # centre leg
        rbox(24.0, TOP - 6.5, 28.75, TOP - 0.5, 1.0),     # pivot ear (stays below the mattress)
        box(24.0, TOP - 6.5, SEAT_D, TOP),
        box(28.0, ARM_BOT, 54.0, ARM_TOP),                # rear arm: back deck rests on it when flat
        box(50.0, 0, 54.0, ARM_TOP),                      # rear leg
    ])
    for u in SLAT_U:
        p = p.difference(box(u - S / 2, TOP - LAP, u + S / 2, TOP + 1))
    p = dogbone(p)
    p = p.difference(rbox(4.5, -5, 21.0, TOP - 7.5, 1.5)).difference(rbox(28.5, -5, 50.0, ARM_BOT, 1.5))
    return p.difference(hole(P)).difference(hole(Q))

def back_rail():   # back frame side: rail with pivot ear and the recline notches underneath
    p = unary_union([box(BACK_X0, TOP - BACK_RAIL_H, BACK_X0 + BACK_D, TOP),
                     rbox(P[0] - 1.25, P[1] - 1.5, BACK_X0 + 1, P[1] + 1.5, 1.0)])
    for u in SLAT_U:
        p = p.difference(box(BACK_X0 + u - S / 2, TOP - LAP, BACK_X0 + u + S / 2, TOP + 1))
    p = dogbone(p)
    for th, x, z in NOTCHES:   # notch = the prop's own outline at that setting, mapped back onto the rail
        pw = prop_world(tip_world(th, x, z)).buffer(0.03, 32)
        p = p.difference(affinity.rotate(pw, -th, origin=P))
    return p.difference(hole(P))

def center_back_rail():
    p = box(BACK_X0, TOP - SLAT_H, BACK_X0 + BACK_D, TOP)
    for u in SLAT_U:
        p = p.difference(box(BACK_X0 + u - S / 2, TOP - LAP, BACK_X0 + u + S / 2, TOP + 1))
    return dogbone(p)

def slat(y0, y1, planes):      # frame: x = across the width, y = height
    p = box(y0, 0, y1, SLAT_H)
    for c in planes:
        p = p.difference(box(c - S / 2, -1, c + S / 2, LAP))
    return dogbone(p)

def prop():
    return LineString([(0, 0), (PROP_L, 0)]).buffer(PROP_W / 2, 32).difference(hole((0, 0)))

PARTS = [  # name, qty, geometry, note
    ("seat-rail", len(SEAT_PLANES), seat_rail(), "seat frame side: legs, pivot ear, rear arm"),
    ("back-rail", 2, back_rail(), f"back frame side: pivot ear + {len(NOTCHES)} recline notches"),
    ("seat-slat", SLAT_N, slat(0.0, W, SEAT_PLANES), "seat deck, on edge, slots down"),
    ("back-slat", SLAT_N, slat(0.6, W - 0.6, BACK_PLANES), "back deck, on edge, slots down; ends rest on the arms when flat"),
    ("prop", 2, prop(), "adjustable back support, bolts to the seat rail arm"),
]
if CENTER:
    PARTS.insert(2, ("back-center-rail", 1, center_back_rail(), "back frame centre (full/queen only)"))
GEOM = {n: g for n, q, g, _ in PARTS}

# ---------------- interference check (side view, per plane) ----------------
def slat_sections(x0, posefn=lambda g: g):
    return unary_union([posefn(box(x0 + u - T / 2, TOP - SLAT_H, x0 + u + T / 2, TOP)) for u in SLAT_U])
def check(label, a, b):
    ov = a.intersection(b).area
    if ov > 0.02: raise SystemExit(f"interference {label}: {ov:.3f} sq in")
seat_r, back_r = GEOM["seat-rail"], GEOM["back-rail"]
prop_folded = prop_world(FOLDED_TIP)
check("bed: seat rail vs back slats", seat_r, slat_sections(BACK_X0))
check("bed: back rail vs seat slats", back_r, slat_sections(0))
check("bed: folded prop vs back rail", prop_folded, back_r)
check("bed: folded prop vs seat slats", prop_folded, slat_sections(0))
for th, x, z in NOTCHES:
    pose = back_pose(th)
    check(f"{th}: seat rail vs back slats", seat_r, slat_sections(BACK_X0, pose))
    check(f"{th}: back rail vs seat slats", pose(back_r), slat_sections(0))
    check(f"{th}: prop vs back rail", prop_world(tip_world(th, x, z)), pose(back_r))
    check(f"{th}: prop vs seat slats", prop_world(tip_world(th, x, z)), slat_sections(0))
    check(f"{th}: prop vs floor", prop_world(tip_world(th, x, z)), box(-10, -10, 100, 0))
for a in range(0, int(max(ANGLES)) + 1, 2):   # the back must swing freely all the way up
    check(f"swing {a}: seat rail vs back slats", seat_r, slat_sections(BACK_X0, back_pose(a)))
    check(f"swing {a}: back rail vs seat slats", back_pose(a)(back_r), slat_sections(0))

# ---------------- nesting: bottom-left fill on 96 x 48 sheets ----------------
SHEET_L, SHEET_W, M, G = 96.0, 48.0, 0.75, 0.75
items = []
for n, q, g, _ in PARTS:
    for i in range(q):
        items.append((f"{n} {i+1}" if q > 1 else n, g))
items.sort(key=lambda it: -(it[1].bounds[2] - it[1].bounds[0]) * (it[1].bounds[3] - it[1].bounds[1]))
sheets = []
def fits(rects, x, y, w, h):
    if x + w > SHEET_L - M + 1e-9 or y + h > SHEET_W - M + 1e-9: return False
    return all(x >= rx + rw + G - 1e-9 or x + w + G <= rx + 1e-9 or y >= ry + rh + G - 1e-9 or y + h + G <= ry + 1e-9
               for rx, ry, rw, rh in rects)
for name, g in items:
    b = g.bounds; w, h = b[2] - b[0], b[3] - b[1]
    for sh in sheets + [None]:
        if sh is None: sh = {"rects": [], "parts": []}; sheets.append(sh)
        xs = {M} | {rx + rw + G for rx, ry, rw, rh in sh["rects"]}
        ys = {M} | {ry + rh + G for rx, ry, rw, rh in sh["rects"]}
        cands = sorted(((x, y) for x in xs for y in ys), key=lambda c: (c[0], c[1]))
        spot = next((c for c in cands if fits(sh["rects"], c[0], c[1], w, h)), None)
        if spot:
            sh["rects"].append((spot[0], spot[1], w, h))
            sh["parts"].append((name, affinity.translate(g, spot[0] - b[0], spot[1] - b[1]))); break
sheets = [s["parts"] for s in sheets]

# ---------------- writers ----------------
import ezdxf
def rings(g):
    for poly in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        yield "CUT_OUTSIDE", list(poly.exterior.coords)
        for r in poly.interiors: yield "CUT_INSIDE", list(r.coords)
def write_dxf(path, items, sheet=False):
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 1; doc.header["$MEASUREMENT"] = 0
    for lay, col in (("CUT_OUTSIDE", 1), ("CUT_INSIDE", 5), ("SHEET_REF_DO_NOT_CUT", 8)): doc.layers.add(lay, color=col)
    msp = doc.modelspace()
    if sheet: msp.add_lwpolyline([(0, 0), (SHEET_L, 0), (SHEET_L, SHEET_W), (0, SHEET_W)], close=True, dxfattribs={"layer": "SHEET_REF_DO_NOT_CUT"})
    for _, g in items:
        for layer, pts in rings(g):
            msp.add_lwpolyline([(round(a, 4), round(b, 4)) for a, b in pts[:-1]], close=True, dxfattribs={"layer": layer})
    doc.saveas(path)
def write_svg(path, items, w, hgt):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}in" height="{hgt}in" viewBox="0 0 {w} {hgt}">',
           f'<rect x="0" y="0" width="{w}" height="{hgt}" fill="none" stroke="#999" stroke-width="0.05"/>']
    for _, g in items:
        d = "".join("M" + " L".join(f"{a:.4f},{hgt-b:.4f}" for a, b in pts[:-1]) + " Z " for _, pts in rings(g))
        out.append(f'<path d="{d}" fill="none" stroke="#000" stroke-width="0.03"/>')
    open(path, "w").write("\n".join(out + ["</svg>"]))

for sub in ("cut", "parts"): os.makedirs(os.path.join(A.out, sub), exist_ok=True)
for i, s in enumerate(sheets, 1):
    write_dxf(os.path.join(A.out, "cut", f"sheet-{i}.dxf"), s, sheet=True)
    write_svg(os.path.join(A.out, "cut", f"sheet-{i}.svg"), s, SHEET_L, SHEET_W)
for n, q, g, _ in PARTS:
    b = g.bounds; g0 = affinity.translate(g, -b[0], -b[1])
    write_dxf(os.path.join(A.out, "parts", f"{n}.dxf"), [(n, g0)])
    write_svg(os.path.join(A.out, "parts", f"{n}.svg"), [(n, g0)], math.ceil(b[2] - b[0]), math.ceil(b[3] - b[1]))
with open(os.path.join(A.out, "parts-list.csv"), "w", newline="") as fh:
    wr = csv.writer(fh); wr.writerow(["part", "qty", "length_in", "height_in", "notes"])
    for n, q, g, note in PARTS:
        b = g.bounds; L, H = sorted([b[2] - b[0], b[3] - b[1]], reverse=True)
        wr.writerow([n, q, f"{L:.2f}", f"{H:.2f}", note])
    wr.writerow(["3/8 x 2-1/2 carriage bolt + 2 fender washers + nylon lock nut", 4, "", "", "2 seat/back pivots, 2 prop pivots"])

# ---------------- previews ----------------
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
def draw(ax, g, fc="#e8c98f", ec="k", lw=0.6, alpha=1):
    for poly in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        ax.add_patch(MPoly(list(poly.exterior.coords), fc=fc, ec=ec, lw=lw, alpha=alpha))
        for r in poly.interiors: ax.add_patch(MPoly(list(r.coords), fc="white", ec=ec, lw=lw))
fig, axs = plt.subplots(len(sheets), 1, figsize=(12, 6.3 * len(sheets)), squeeze=False)
for i, (ax, s) in enumerate(zip(axs[:, 0], sheets), 1):
    ax.add_patch(MPoly([(0, 0), (SHEET_L, 0), (SHEET_L, SHEET_W), (0, SHEET_W)], fc="#f6f6f6", ec="#888"))
    for name, g in s:
        draw(ax, g); c = g.representative_point(); ax.text(c.x, c.y, name, fontsize=8, color="#a00")
    ax.set_xlim(-1, SHEET_L + 1); ax.set_ylim(-1, SHEET_W + 1); ax.set_aspect("equal")
    ax.set_title(f"Sheet {i} of {len(sheets)}  (4x8 23/32 OSB, strong axis left-right)")
fig.tight_layout(); fig.savefig(os.path.join(A.out, "nesting.png"), dpi=110); plt.close(fig)

def side(ax, th, title):
    pose = back_pose(th) if th else (lambda g: g)
    draw(ax, seat_r, fc="#e8c98f")
    draw(ax, slat_sections(0), fc="#a0522d")
    draw(ax, pose(back_r), fc="#d9b06e", alpha=0.9)
    draw(ax, slat_sections(BACK_X0, pose), fc="#a0522d")
    tip = FOLDED_TIP if not th else tip_world(*next((a, x, z) for a, x, z in NOTCHES if a == th))
    draw(ax, prop_world(tip), fc="#6b8e23", alpha=0.85)
    draw(ax, box(0, TOP, SEAT_D, TOP + 6), fc="#9fc3e8", ec="#467", alpha=0.5)
    draw(ax, pose(box(BACK_X0, TOP, BACK_X0 + BACK_D, TOP + 6)), fc="#9fc3e8", ec="#467", alpha=0.5)
    for c in (P, Q): ax.plot(*c, "ko", ms=3)
    ax.set_xlim(-2, 58); ax.set_ylim(-1, 44); ax.set_aspect("equal"); ax.grid(alpha=0.3); ax.set_title(title, fontsize=10)
fig, axs = plt.subplots(2, 2, figsize=(14, 10))
side(axs[0, 0], 0, f"Bed: flat {SEAT_D+GAP+BACK_D}\" deep, deck top {TOP:g}\", prop folded")
for ax, (th, x, z) in zip([axs[0, 1], axs[1, 0], axs[1, 1]], NOTCHES):
    top = pose_top = affinity.rotate(Point(BACK_X0 + BACK_D, TOP), th, origin=P).coords[0]
    side(ax, th, f"Sofa, notch at {th:g}°: back frame top {top[1]:.1f}\" high")
fig.tight_layout(); fig.savefig(os.path.join(A.out, "side-views.png"), dpi=100); plt.close(fig)

print(f"prop length {PROP_L} (hole to tip centre); notches at back-rail x:",
      [f"{th:g}deg@{x-BACK_X0:.2f}" for th, x, z in NOTCHES])
for i, s in enumerate(sheets, 1):
    print(f"sheet {i}: {len(s)} parts, {100*sum(g.area for _, g in s)/(SHEET_L*SHEET_W):.0f}% used")
for n, q, g, _ in PARTS:
    b = g.bounds; print(f"{n} x{q}: {b[2]-b[0]:.2f} x {b[3]-b[1]:.2f} {g.geom_type}")
