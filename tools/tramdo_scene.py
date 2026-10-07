"""Tram Distribution Office: the two tram yards (small trams, large trams).

    blender -b --python tools/tramdo_scene.py -- <texdir> <itemdir> <previewdir>

A Soviet tram depot turned freight office: a long brick shed with open portals over the parking
lanes, a two-storey dispatch wing ("ТРАМГРУЗ", tram freight) between the shed and the station track,
and a traction substation, a sand tower and lamp masts wherever the tracks leave room. The track
layouts are the game's own (tools/tramdo_layout.py): the small yard is the tram end station
(6 lanes), the large yard the big tram depot (8 lanes) stretched for the long tram sets. The office
holds one tram set per parking lane.

The model holds no rails, wires or ground plate: like the game's own depot and end station (whose
models are only the buildings), the game itself draws the tram track and trolley wires along the
$CONNECTION_TRAMROAD_DEAD / _TRAMTROLLEYS_DEAD pieces, joined by smooth curves, on the footprint it
paves - a raised plate would bury them. A strip below ground stretches the model's box over the
whole footprint, as the game's depot does. Buildings other than the shed are placed by a clearance
search against every track, wire and road piece of the layout, so they never stand on a track.

The previews add, in a separate mesh that is never exported, the dark paving and rails along the
layout's own tram paths (its PID points, smoothed), so the pictures look like the yard in game.

Writes <itemdir>/<object>/{model.nmf, building.ini, renderconfig.ini, building.bbox, building.fire,
imagegui.png}, the shared <itemdir>/material/ (Space Race kit textures, build/space_textures) and
previews to <previewdir>. Ground level stays at y = 0 - the trams run there - so unlike the Space
Race kit there is no podium lift.
"""
import math
import os
import shutil
import sys

import bpy

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import nmf  # noqa: E402
import mmkit  # noqa: E402
import srkit as K  # noqa: E402
from srkit import (CONC, WHITE, GREY, GLASS, STUCCO, BRICK, ROOF, ASPH, GROUND, METAL, DARK, GLOW, CORR,  # noqa: E402
                   HAZARD)
from space_palette import MATS, EMISSIVE  # noqa: E402
import tramdo_layout as L  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
TEXDIR = argv[0] if len(argv) > 0 else 'build/space_textures'
ITEMDIR = argv[1] if len(argv) > 1 else 'mod/packages/tram_do'
PREVIEW = argv[2] if len(argv) > 2 else 'build/tramdo'

GAUGE = 1.524
FOOT = -0.6          # walls and legs reach this far below ground, so slopes never show a gap
CARS_PER_SET = 7     # office places per parking lane: every wagon of a set takes a place too
TRACK_CLEAR = 2.3    # buildings keep this far from a track's centre line, 1.0 from a trolley wire


# ----------------------------------------------------------------- layout --

class Yard:
    """The layout seen from its lanes: u runs along the parking lanes, v across them."""

    def __init__(self, lines, parsed):
        self.lines, self.parsed = lines, parsed
        self.bounds = L.bounds(parsed)
        lanes = parsed['$VEHICLE_PARKING']
        self.axis = 'x' if sum(abs(a[0] - c[0]) for a, c in lanes) > sum(abs(a[2] - c[2]) for a, c in lanes) else 'z'
        self.lanes = [((a[0], a[2]), (c[0], c[2])) for a, c in lanes]
        self.lanes_v = sorted(self.v(p) for p, _q in self.lanes)
        self.u0 = min(min(self.u(p), self.u(q)) for p, q in self.lanes)
        self.u1 = max(max(self.u(p), self.u(q)) for p, q in self.lanes)
        st = parsed.get('$VEHICLE_STATION', [])
        self.station = [((a[0], a[2]), (c[0], c[2])) for a, c in st]
        self.paths = tram_paths(lines, parsed)

    def u(self, p):
        return p[0] if self.axis == 'x' else p[1]

    def v(self, p):
        return p[1] if self.axis == 'x' else p[0]

    def game(self, u, v):
        return (u, v) if self.axis == 'x' else (v, u)

    def rect(self, u0, v0, u1, v1):
        (x0, z0), (x1, z1) = self.game(u0, v0), self.game(u1, v1)
        return min(x0, x1), min(z0, z1), max(x0, x1), max(z0, z1)


def pid_points(lines, keyword):
    """'<keyword> <pid> x y z' lines -> {pid: [(x, z), ...]} in file order."""
    out = {}
    for line in lines:
        t = line.split()
        if t and t[0] == keyword:
            out.setdefault(int(t[1]), []).append((float(t[2]), float(t[4])))
    return out


def _turn(a, b, c):
    d0, d1 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
    n0, n1 = math.hypot(*d0), math.hypot(*d1)
    if n0 < 1e-6 or n1 < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (d0[0] * d1[0] + d0[1] * d1[1]) / (n0 * n1)))))


def _route(before, ends, after):
    """A tram's way: approach points, the lane or station track (ends ordered to suit), leaving points.
    A track end that would make the path double back is dropped (the approach already reaches into
    the lane); a reversal at a PID point splits the path there (the tram backs out of a stub)."""
    p, q = ends
    if before:
        if math.dist(before[-1], q) < math.dist(before[-1], p):
            p, q = q, p
    elif after and math.dist(after[0], p) < math.dist(after[0], q):
        p, q = q, p
    pts = list(before)
    for e in (p, q):
        if len(pts) >= 1 and math.dist(pts[-1], e) < 0.5:
            continue
        pts.append(e)
    pts += after
    keep = [pts[0]]
    marks = {p, q}
    for k in range(1, len(pts) - 1):
        if pts[k] in marks and _turn(keep[-1], pts[k], pts[k + 1]) > 110:
            continue
        keep.append(pts[k])
    keep.append(pts[-1])
    out, cur = [], [keep[0]]
    for k in range(1, len(keep) - 1):
        cur.append(keep[k])
        if _turn(keep[k - 1], keep[k], keep[k + 1]) > 110:
            out.append(cur)
            cur = [keep[k]]
    cur.append(keep[-1])
    out.append(cur)
    return [c for c in out if len(c) >= 2]


def tram_paths(lines, parsed):
    """Where the trams drive, from the layout's own points: each lane's approach, the lane and its
    way out; the station track with its entry and detour."""
    approach = pid_points(lines, '$VEHICLE_PARKING_ADVANCED_POINT_PID')
    leave = pid_points(lines, '$PARKING_NOT_BLOCK_DETOUR_POINT_PID')
    paths = []
    for i, (a, c) in enumerate(parsed['$VEHICLE_PARKING']):
        paths += _route(approach.get(i, []), ((a[0], a[2]), (c[0], c[2])), leave.get(i, []))
    entry = pid_points(lines, '$VEHICLE_STATION_NOT_BLOCK_ENTRY_POINT_PID').get(0, [])
    detour = pid_points(lines, '$STATION_NOT_BLOCK_DETOUR_POINT_PID').get(0, [])
    for a, c in parsed.get('$VEHICLE_STATION', []):
        paths += _route(entry, ((a[0], a[2]), (c[0], c[2])), detour)
    return paths


def smooth(pts, step=0.6):
    """Centripetal Catmull-Rom through the points, sampled about every `step` metres. Long gaps (the
    lanes, the station track) get points along them first, so they stay straight instead of bowing."""
    dense = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = math.dist(a, b)
        if n > 12.0:
            ts = [2.5 / n] + [k * 5.0 / n for k in range(1, int(n / 5.0)) if 2.5 < k * 5.0 < n - 2.5] + [1 - 2.5 / n]
            dense += [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in ts]
        dense.append(b)
    pts = dense
    if len(pts) < 3:
        n = max(1, int(math.dist(pts[0], pts[-1]) / step))
        return [(pts[0][0] + (pts[-1][0] - pts[0][0]) * k / n, pts[0][1] + (pts[-1][1] - pts[0][1]) * k / n) for k in range(n + 1)]
    P = [(2 * pts[0][0] - pts[1][0], 2 * pts[0][1] - pts[1][1])] + list(pts) + [(2 * pts[-1][0] - pts[-2][0], 2 * pts[-1][1] - pts[-2][1])]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + max(math.dist(p0, p1), 1e-3) ** 0.5
        t2 = t1 + max(math.dist(p1, p2), 1e-3) ** 0.5
        t3 = t2 + max(math.dist(p2, p3), 1e-3) ** 0.5
        n = max(2, int(math.dist(p1, p2) / step))
        for k in range(n):
            t = t1 + (t2 - t1) * k / n

            def lerp(a, b, ta, tb):
                w = (t - ta) / (tb - ta)
                return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)
            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    out.append(pts[-1])
    return out


def obstacles(y):
    """Points every 0.5 m, with their clearance, on everything a building must keep off: the trams'
    paths, every tram track and trolley wire piece, the station track and the access road."""
    segs = []
    for path in y.paths:
        s = smooth(path, 1.0)
        segs += [((a, b), TRACK_CLEAR) for a, b in zip(s, s[1:])]
    for kw, clear in (('$CONNECTION_TRAMROAD_DEAD', TRACK_CLEAR), ('$CONNECTION_TRAMTROLLEYS_DEAD', 1.0),
                      ('$CONNECTION_ROAD', 3.0), ('$VEHICLE_STATION', TRACK_CLEAR), ('$VEHICLE_PARKING', TRACK_CLEAR)):
        for piece in y.parsed.get(kw, []):
            if len(piece) == 2:
                segs.append((((piece[0][0], piece[0][2]), (piece[1][0], piece[1][2])), clear))
    pts = []
    for (a, b), clear in segs:
        n = max(1, int(math.dist(a, b) / 0.5))
        pts += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n, clear) for k in range(n + 1)]
    return pts


def rect_clear(r, obs, rects, margin=0.8):
    """Whether rectangle r keeps its clearance from every obstacle point and placed rectangle."""
    for o in rects:
        if r[0] < o[2] + margin and o[0] < r[2] + margin and r[1] < o[3] + margin and o[1] < r[3] + margin:
            return False
    for x, z, c in obs:
        dx = max(r[0] - x, 0.0, x - r[2])
        dz = max(r[1] - z, 0.0, z - r[3])
        if dx * dx + dz * dz < c * c:
            return False
    return True


def find_spot(y, w, d, obs, rects, avoid=(), spread=0.0):
    """A free w x d rectangle (either way round) inside the footprint, as near a footprint corner as
    possible and at least `spread` metres from the centres in `avoid`. None if nothing fits."""
    x0, z0, x1, z1 = y.bounds
    corners = [(x0, z0), (x0, z1), (x1, z0), (x1, z1)]
    cands = []
    for ww, dd in ((w, d), (d, w)):
        x = x0 + 0.5
        while x + ww <= x1 - 0.5:
            z = z0 + 0.5
            while z + dd <= z1 - 0.5:
                c = (x + ww / 2, z + dd / 2)
                if all(math.dist(c, a) >= spread for a in avoid):
                    cands.append((min(math.dist(c, k) for k in corners), (x, z, x + ww, z + dd)))
                z += 1.0
            x += 1.0
    for _score, r in sorted(cands):
        if rect_clear(r, obs, rects):
            return r
    return None


# ------------------------------------------------- preview track (not exported) --

def ribbon(b, mat, pts, width, y, offset=0.0):
    """A flat strip along dense points (a rail), offset sideways from the centre line."""
    bm = b.master[mat]
    rows = []
    for k, (x, z) in enumerate(pts):
        p, q = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
        dx, dz = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(dx, dz) or 1.0
        nx, nz = -dz / ln, dx / ln
        rows.append([bm.verts.new(mmkit.G(x + nx * o, y, z + nz * o)) for o in (offset - width / 2, offset + width / 2)])
    for (a, c), (d, e) in zip(rows, rows[1:]):
        f = bm.faces.new((a, c, e, d))
        f.material_index = mat
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()


def preview_yard(b, y):
    """The terrain, the dark paving the game lays over the footprint, and rails along the trams'
    paths - previews only."""
    x0, z0, x1, z1 = y.bounds
    K.slab(b, GROUND, x0 - 16, z0 - 16, x1 + 16, z1 + 16, -0.6, 0.0)
    K.slab(b, ASPH, x0, z0, x1, z1, -0.2, 0.012)
    for path in y.paths:
        s = smooth(path)
        for o in (-GAUGE / 2, GAUGE / 2):
            ribbon(b, METAL, s, 0.1, 0.03, offset=o)


# ------------------------------------------------------------------ model --

def shed(b, x0, z0, x1, z1, lanes_z, h=8.4):
    """The tram shed (lanes along x): brick long walls, open portals over each lane at both ends,
    gable roof and lantern. No floor, rails or wires - the game draws the track and wire through it."""
    for zw in (z0, z1):
        K.slab(b, BRICK, x0, zw - 0.25, x1, zw + 0.25, FOOT, h)
        for x in range(int(x0) + 3, int(x1) - 1, 6):                     # pilasters and tall windows
            K.slab(b, CONC, x - 0.35, zw - 0.4, x + 0.35, zw + 0.4, FOOT, h + 0.2)
            K.slab(b, GLASS, x + 1.2, zw - 0.3, x + 3.6, zw + 0.3, 2.4, h - 1.6)
    pier = 0.6
    for xe in (x0, x1):
        edges = [z0 + 0.25] + [zz for lz in lanes_z for zz in (lz - 1.85, lz + 1.85)] + [z1 - 0.25]
        for za, zb in zip(edges[0::2], edges[1::2]):                     # piers between portals
            if zb - za > 0.05:
                K.slab(b, BRICK, xe - pier, za, xe + pier, zb, FOOT, h)
        K.slab(b, BRICK, xe - pier, z0, xe + pier, z1, 5.6, h)             # lintel over the portals
        for lz in lanes_z:                                               # arched heads, rendered as brick arcs
            for k in range(5):
                a = math.pi * (k + 0.5) / 5
                K.slab(b, CONC, xe - pier - 0.05, lz - 1.85 * math.cos(a) - 0.25, xe + pier + 0.05,
                       lz - 1.85 * math.cos(a) + 0.25, 5.1 + 0.5 * math.sin(a), 5.6)
    W = z1 - z0
    ridge = min(W * 0.22, 6.0)
    ang = math.degrees(math.atan2(ridge, W / 2))
    half = math.hypot(W / 2, ridge) + 0.5
    cz, Ls = (z0 + z1) / 2, x1 - x0
    for s in (-1, 1):
        b.box(ROOF, ((x0 + x1) / 2, h + ridge / 2, cz + s * W / 4), (Ls + 1.0, 0.3, half), pitch=s * ang)
    for xe in (x0, x1):                                                  # gable ends above the lintels
        K.ngon_prism(b, BRICK, [(-W / 2, 0), (W / 2, 0), (0, ridge)], -0.3, 0.3, center=(xe, h, cz), yaw=90, pitch=-90)
    K.slab(b, GLASS, x0 + 2, cz - 1.6, x1 - 2, cz + 1.6, h + ridge - 0.2, h + ridge + 1.1)   # roof lantern
    K.slab(b, ROOF, x0 + 1.6, cz - 2.0, x1 - 1.6, cz + 2.0, h + ridge + 1.1, h + ridge + 1.4)
    return h + ridge


def dispatch(b, x0, z0, x1, z1):
    """Two-storey dispatch office, sign and star facing +z (the station track)."""
    top = K.block(b, x0, z0, x1, z1, 2, wall=STUCCO, roof=ROOF)
    K.slab(b, CONC, x0 - 0.2, z1, x1 + 0.2, z1 + 0.3, 0, 0.9)
    K.door(b, (x0 + x1) / 2, z1 + 0.15, 2.4, 2.8)
    K.sign(b, 'ТРАМГРУЗ', ((x0 + x1) / 2, top + 1.0, z1 + 0.2), 1.5, board=(x1 - x0 - 2.0, 2.1, WHITE))
    K.star(b, ((x0 + x1) / 2, top + 3.4, z1 + 0.15), 1.0)
    for x in (x0 + 1.5, x1 - 1.5):
        b.box(GLOW, (x, 3.0, z1 + 0.2), (0.4, 0.4, 0.1))
    return top


def substation(b, r):
    """Traction substation, the trolley wires' feed: a brick block, transformers on the roof."""
    x0, z0, x1, z1 = r
    top = K.block(b, x0, z0, x1, z1, 1, wall=BRICK, roof=ROOF, floor_h=4.2, base=FOOT)
    long_x = (x1 - x0) > (z1 - z0)
    if long_x:
        K.slab(b, GREY, (x0 + x1) / 2 - 0.9, z1, (x0 + x1) / 2 + 0.9, z1 + 0.12, 0, 2.6)    # door
        b.box(HAZARD, (x1 - 1.3, 3.2, z1 + 0.13), (0.7, 0.7, 0.04))
    else:
        K.slab(b, GREY, x0 - 0.12, (z0 + z1) / 2 - 0.9, x0, (z0 + z1) / 2 + 0.9, 0, 2.6)
        b.box(HAZARD, (x0 - 0.13, 3.2, z1 - 1.3), (0.04, 0.7, 0.7))
    for k in range(3):                                                   # transformers on the roof
        f = (k + 1) / 4
        c = (x0 + (x1 - x0) * f, (z0 + z1) / 2) if long_x else ((x0 + x1) / 2, z0 + (z1 - z0) * f)
        b.box(GREY, (c[0], top + 0.4, c[1]), (1.2, 0.8, 1.2))
    return top


def sand_tower(b, sx, sz, toward):
    """The depot's sand tower, its chute reaching toward the nearest track."""
    for dx, dz in ((-1.1, -1.1), (1.1, -1.1), (1.1, 1.1), (-1.1, 1.1)):
        b.rod(GREY, (sx + dx, FOOT, sz + dz), (sx + dx * 0.8, 6.0, sz + dz * 0.8), 0.12, segs=5)
    b.cyl(CORR, (sx, 6.0, sz), 1.6, 4.2, segs=14)
    b.cyl(ROOF, (sx, 10.2, sz), 1.75, 0.9, segs=14, r2=0.3)
    dx, dz = toward[0] - sx, toward[1] - sz
    n = math.hypot(dx, dz) or 1.0
    reach = min(n - 0.5, 3.2)
    b.rod(METAL, (sx + dx / n * 1.2, 7.0, sz + dz / n * 1.2), (sx + dx / n * reach, 5.8, sz + dz / n * reach), 0.12, segs=6)


def shed_extent(y):
    """The shed's length along the lanes: the lanes plus 1.6 m, cut back where the trams' paths are
    still curving into or out of the lanes (a point more than 1 m off every lane's line)."""
    u0, u1 = y.u0 - 1.6, y.u1 + 1.6
    v0, v1 = y.lanes_v[0] - 2.0, y.lanes_v[-1] + 2.1
    mid = (y.u0 + y.u1) / 2
    for path in y.paths:
        for p in smooth(path, 1.0):
            pu, pv = y.u(p), y.v(p)
            if not (v0 < pv < v1) or min(abs(pv - lv) for lv in y.lanes_v) <= 1.0:
                continue
            if pu > mid:
                u1 = min(u1, pu - 2.0)
            else:
                u0 = max(u0, pu + 2.0)
    return u0, u1, v0, v1


def yard(b, y):
    """The buildings. Returns the rectangles (x0, z0, x1, z1) they occupy."""
    rects = []
    obs = obstacles(y)
    su0, su1, sv0, sv1 = shed_extent(y)
    uc, vc = (su0 + su1) / 2, (sv0 + sv1) / 2
    gx, gz = y.game(uc, vc)
    out = K.place(b, lambda tb: shed(tb, -(su1 - su0) / 2, sv0 - vc, (su1 - su0) / 2, sv1 - vc, [v - vc for v in y.lanes_v]),
                  center=(gx, 0, gz), yaw=0 if y.axis == 'x' else 90)
    roof = out
    rects.append(y.rect(su0, sv0, su1, sv1))
    b.fire.append((gx, roof - 1.0, gz))

    # dispatch wing between the shed and the station track, facing the station
    if y.station:
        (sa, sb) = y.station[0]
        st_v = (y.v(sa) + y.v(sb)) / 2
        st_u0, st_u1 = sorted((y.u(sa), y.u(sb)))
        side = 1 if st_v > vc else -1
        near = sv1 + 0.25 if side > 0 else sv0 - 0.25
        gap = abs((st_v - side * 1.6) - near) - 0.8
        depth = min(4.9, gap)
        ou0, ou1 = max(st_u0, su0), min(st_u1, su1)
        length = min(18.0, max(10.0, (ou1 - ou0) * 0.6))
        du = (ou0 + ou1) / 2
        dv = near + side * depth / 2
        dx, dz = y.game(du, dv)
        yaw = (0 if side > 0 else 180) if y.axis == 'x' else (90 if side > 0 else -90)
        if depth >= 3.5:
            top = K.place(b, lambda tb: dispatch(tb, -length / 2, -depth / 2, length / 2, depth / 2), center=(dx, 0, dz), yaw=yaw)
            r = y.rect(du - length / 2 - 0.3, min(near, near + side * (depth + 0.4)), du + length / 2 + 0.3, max(near, near + side * (depth + 0.4)))
            rects.append(r)
            b.fire.append((dx, top - 1.0, dz))
            fu, fv = du - length / 2 - 1.6, near + side * (depth - 0.6)            # flagpole by its front corner
            fx, fz = y.game(fu, fv)
            if rect_clear((fx - 0.3, fz - 0.3, fx + 0.3, fz + 0.3), obs, rects[:-1]):
                K.flagpole(b, fx, fz, h=10.0)
                rects.append((fx - 0.3, fz - 0.3, fx + 0.3, fz + 0.3))
        else:
            print('  no room for the dispatch wing (%.1f m)' % depth)

    placed = []
    r = find_spot(y, 4.4, 7.0, obs, rects)
    if r:
        substation(b, r)
        rects.append(r)
        placed.append(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2))
    else:
        print('  no room for the substation')
    r = find_spot(y, 3.8, 3.8, obs, rects, avoid=placed, spread=12.0)
    if r:
        c = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        nearest = min((p for path in y.paths for p in smooth(path, 1.0)), key=lambda p: math.dist(p, c))
        sand_tower(b, c[0], c[1], nearest)
        rects.append(r)
        placed.append(c)
    else:
        print('  no room for the sand tower')
    for _k in range(2):
        r = find_spot(y, 1.6, 1.6, obs, rects, avoid=placed, spread=20.0)
        if r:
            c = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
            K.lamp_mast(b, c[0], c[1], h=14.0, head=2.0)
            rects.append(r)
            placed.append(c)

    # below ground, out of sight: stretches the model's box over the whole footprint, as the
    # game's depot model does with a strip along its front edge
    x0, z0, x1, z1 = y.bounds
    K.slab(b, DARK, x0, z1 - 0.3, x1, z1, -1.2, -0.4)
    K.slab(b, DARK, x0, z0, x1, z0 + 0.3, -1.2, -0.4)
    return rects


# ----------------------------------------------------------------- files --

RENDERCONFIG = '''$TYPE_WORKSHOP
 MODEL model.nmf
 MATERIAL ../material/%(n)s.mtl
 MATERIALEMISSIVE ../material/%(n)s_e.mtl
 LIFE 4000.000000
 EXPLOSION_GROUP 2
 DERBIS_FALLING_FX buildingfall1 1.400000
 DERBIS_FALLED_FX buildingfall2 1.400000
 DERBIS_FALLED_SFX collapse
 DERBIS_NUM 40
 DERBIS_FALLING_FX_MAXTIME 1.000000
 DERBIS_SCALE 1.200000
 DERBIS_MESH buildings/buildingwreck1.nmf buildings/buildingwreck.mtl
 DERBIS_MESH buildings/buildingwreck2.nmf buildings/buildingwreck.mtl
 END
'''.replace('\n', '\r\n')


def mtl(names, emissive=False):
    out = []
    for name in names:
        out.append('$SUBMATERIAL %s' % name)
        out.append('$TEXTURE_MTL 0 %s.dds' % name)
        if emissive:
            out.append('$TEXTURE_MTL 1 %s.dds' % EMISSIVE.get(name, 'sr_black'))
        else:
            out.append('$TEXTURE 1 buildings/blankspecular.dds')
        out += ['$TEXTURE 2 buildings/blankbump.dds', '', '$DIFFUSECOLOR 0.92 0.92 0.92 1.0',
                '$SPECULARCOLOR %s 1.0' % ('0.8 0.8 0.8' if name in ('sr_metal', 'sr_white') else '0.3 0.3 0.3'),
                '$AMBIENTCOLOR 1.0 1.0 1.0 1.0', '', '$SPECULARPOWER 4.0', '']
    out += ['$END', '']
    return '\r\n'.join(out)


# Construction: fixed amounts per phase, not $COST_RESOURCE_AUTO, which scales with the model (with
# the below-ground strips over the whole yard it asked ~1300 t of concrete). The game's train office
# costs 2791 workdays, 81 t concrete, 62 gravel, 49 asphalt, 159 bricks, 53 boards, 19 steel; the
# small yard costs less, the large one (COST_SCALE) about as much. The construction stops are the
# source building's own (tramdo_layout.cost_stops).
COSTS = [
    ('SOVIET_CONSTRUCTION_GROUNDWORKS 0.0', [('workers', 600), ('concrete', 50), ('gravel', 45), ('asphalt', 30)]),
    ('SOVIET_CONSTRUCTION_BRICKS_LAYING 1.0', [('workers', 1200), ('bricks', 110), ('boards', 35)]),
    ('SOVIET_CONSTRUCTION_STEEL_LAYING 1.0', [('workers', 400), ('steel', 14)]),
]
COST_SCALE = {'tramdo_small': 1.0, 'tramdo_large': 1.25}


def building_ini(key, y):
    size = L.SIZES[key]
    places = len(y.lanes) * CARS_PER_SET
    out = ['$NAME_STR "%s"' % size['name'], '$TYPE_DISTRIBUTION_OFFICE', '$SUBTYPE_TRAM',
           '$MENU_SFX building_tram_depot', '$WORKING_VEHICLES_NEEDED %d' % places, '']
    out += y.lines + ['']
    k = COST_SCALE[key]
    stops = L.cost_stops(key)
    for work, resources in COSTS:
        out += ['------------------', '$COST_WORK ' + work, '$COST_WORK_BUILDING_ALL']
        out += ['$COST_WORK_VEHICLE_STATION %.2f 0.0 %.2f %.2f 0.0 %.2f' % s for s in stops]
        out += ['$COST_RESOURCE %s %d' % (r, round(n * k)) for r, n in resources]
    out += ['------------------', '', 'end', '']
    return '\r\n'.join(out)


def main():
    mmkit.clear_scene()
    os.makedirs(ITEMDIR, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    matdir = os.path.join(ITEMDIR, 'material')
    if os.path.isdir(matdir):                    # only what this build uses
        shutil.rmtree(matdir)
    os.makedirs(matdir)
    bmats = mmkit.blender_materials(TEXDIR, MATS)
    mmkit.lighting()
    used_all = set()
    for key in L.SIZES:
        lines, parsed = L.layout(key)
        y = Yard(lines, parsed)
        print('%s: %d lanes along %s, footprint %s' % (key, len(y.lanes), y.axis, ['%.1f' % v for v in y.bounds]))
        b = K.builder(seed=sum(map(ord, key)))
        yard(b, y)
        shapes, used = b.export_shapes(prefix='td_')
        used_all.update(used)
        model = nmf.Model(); model.materials = used; model.shapes = shapes
        adir = os.path.join(ITEMDIR, key)
        os.makedirs(adir, exist_ok=True)
        nmf.write(model, os.path.join(adir, 'model.nmf'))
        bbox = mmkit.model_bbox(shapes)
        mmkit.write_bbox_file(os.path.join(adir, 'building.bbox'), shapes)
        mmkit.write_fire_file(os.path.join(adir, 'building.fire'), b.fire)
        mmkit.write_text(os.path.join(adir, 'building.ini'), building_ini(key, y))
        mmkit.write_text(os.path.join(adir, 'renderconfig.ini'), RENDERCONFIG % {'n': key})
        mmkit.write_text(os.path.join(matdir, key + '.mtl'), mtl(used))
        mmkit.write_text(os.path.join(matdir, key + '_e.mtl'), mtl(used, emissive=True))
        pb = K.builder(seed=1)                   # paving and rails as the game draws them: previews only
        preview_yard(pb, y)
        pb.export_shapes()                       # triangulates and maps; the shapes themselves are dropped
        obs = b.preview_objects(bmats, key) + pb.preview_objects(bmats, key + '_yard')
        pos, tgt = mmkit.frame_camera(bbox, azimuth_deg=-35, elevation_deg=32, fill=1.1)
        mmkit.render(os.path.join(PREVIEW, key + '.png'), pos, tgt, (1400, 900), samples=32)
        pos, tgt = mmkit.frame_camera(bbox, azimuth_deg=-30, elevation_deg=40, fill=0.95)
        mmkit.render(os.path.join(PREVIEW, key + '_icon.png'), pos, tgt, (384, 384), transparent=True, samples=24)
        mmkit.save_scaled_png(os.path.join(PREVIEW, key + '_icon.png'), os.path.join(adir, 'imagegui.png'), 96, 96)
        pos, tgt = mmkit.frame_camera(bbox, azimuth_deg=-35, elevation_deg=30, fill=0.8)      # poster cut-out
        mmkit.render(os.path.join(PREVIEW, key + '_cut.png'), pos, tgt, (1800, 1200), transparent=True, samples=32)
        top = mmkit.frame_camera(bbox, azimuth_deg=180, elevation_deg=89.5, fill=1.0)     # plan view, north up
        mmkit.render(os.path.join(PREVIEW, key + '_top.png'), top[0], top[1], (1400, 700), samples=16,
                     ortho=max(bbox[3] - bbox[0], (bbox[5] - bbox[2]) * 2.0) + 10)
        for ob in obs:
            bpy.data.objects.remove(ob)
        print('%-13s tris=%6d nodes=%2d bbox=%s' % (key, sum(s.nt for s in shapes), len(shapes), ['%.0f' % v for v in bbox]))
        b.free()
        pb.free()
    for name in sorted(used_all) + ['sr_black', 'sr_glass_e', 'sr_stucco_e']:
        src = os.path.join(TEXDIR, name + '.dds')
        if os.path.exists(src):
            shutil.copy(src, os.path.join(matdir, name + '.dds'))
    print('tram yards done ->', ITEMDIR)


main()
