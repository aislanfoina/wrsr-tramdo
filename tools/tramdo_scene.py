"""Tram Distribution Office: the two tram yards (small trams, large trams).

    blender -b --python tools/tramdo_scene.py -- <texdir> <itemdir> <previewdir>

A Soviet tram depot turned freight office: a long brick shed with open portals over the four parking
lanes, a two-storey dispatch wing ("ТРАМГРУЗ", tram freight) between the shed and the front track,
a traction substation, a sand tower, lamp masts and a fence in the corners the tracks leave free. The
track layout is the game's own small tram depot (tools/tramdo_layout.py): the small yard uses it as
it is, the large yard stretched 1.5x lengthwise for the long tram sets.

The model holds no rails, wires or ground plate: like the game's own depot and end station (whose
models are only the buildings), the game itself draws the tram track and trolley wires along the
$CONNECTION_TRAMROAD_DEAD / _TRAMTROLLEYS_DEAD pieces, joined by smooth curves, on the flattened
terrain - a raised plate would bury them. A strip below ground stretches the model's box over the
whole footprint, as the game's depot does. The previews add, in a separate mesh that is never
exported, ground and curved track roughly where the game draws them (track_plan), so the pictures
look like the yard in game.

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
from srkit import (CONC, WHITE, GREY, GLASS, STUCCO, BRICK, ROOF, GROUND, METAL, DARK, GLOW, CORR,  # noqa: E402
                   HAZARD)
from space_palette import MATS, EMISSIVE  # noqa: E402
import tramdo_layout as L  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
TEXDIR = argv[0] if len(argv) > 0 else 'build/space_textures'
ITEMDIR = argv[1] if len(argv) > 1 else 'mod/packages/tram_do'
PREVIEW = argv[2] if len(argv) > 2 else 'build/tramdo'

GAUGE = 1.524
WIRE_Y = 5.8         # trolley wire height in the previews
FOOT = -0.6          # walls and legs reach this far below ground, so slopes never show a gap
VEHICLES = {'tramdo_small': 24, 'tramdo_large': 40}     # office places: every wagon of a set counts as one


# ------------------------------------------------- preview track (not exported) --

def lane_lines(parsed):
    """The parking lanes as (z, west x, east x), south to north."""
    return sorted(((a[2] + c[2]) / 2, min(a[0], c[0]), max(a[0], c[0])) for a, c in parsed['$VEHICLE_PARKING'])


def track_plan(parsed, s):
    """The yard's tracks roughly as the game joins the layout's pieces, for the previews only: a list
    of (corner points, arc radius at each inner corner). Trams come in from the street on the north
    track (z 6.84), run west along the front, down the west spine and into a lane, leave the shed
    eastward and join the exit curve to the street's south track (z 3.17); the station track runs in
    front of the dispatch wing as a passing loop. Follows the vanilla depot's paths
    ($VEHICLE_PARKING_ADVANCED_POINT_PID etc.), x stretched by s like the layout."""
    _x0, _z0, x1, _z1 = L.bounds(parsed)
    street, z_in, z_out, z_front = x1 + 1.0, 6.84, 3.17, 9.7
    xw, xe = -35.6 * s, 34.6 * s                 # west spine, east spine
    lanes = lane_lines(parsed)
    plan = []
    zs, _w, _e = lanes[0]                        # the southern lane: the whole loop, street to street
    plan.append(([(street, z_in), (33.3 * s, z_in), (26.0 * s, z_front), (xw, z_front), (xw, zs), (xe, zs),
                  (xe, z_out), (street, z_out)], [12, 12, 6, 6, 5, 7.5]))
    rk = 7.5                                     # the exit curve, east spine -> street
    ck = (xe + rk, z_out - rk)
    joins = iter((40.0, 55.0, 70.0))
    for z, _w, _e in lanes[1:]:
        pts, radii = [(xw, z + 6.0), (xw, z)], [6]
        if z + 5.0 <= ck[1]:                     # onto the east spine below the exit curve
            pts += [(xe, z), (xe, z + 5.0)]
            radii.append(5)
        else:                                    # onto the exit curve itself, like a turnout
            th = math.radians(next(joins))
            j = (ck[0] - rk * math.cos(th), ck[1] + rk * math.sin(th))
            pts += [(j[0] - (j[1] - z) * math.tan(th), z), j]
            radii.append(8)
        plan.append((pts, radii))
    # the station track: a passing loop beside the front track, off the inbound track at the east end
    # and back into the front track at the west end (the game's own station path reverses in a short
    # stub there, which reads as a dead end when drawn)
    plan.append(([(33.3 * s, z_in), (-14.0 * s, z_in), (-21.0 * s, z_front), (-26.0 * s, z_front)], [12, 12]))
    return plan


def fillet(pts, radii, step=0.6):
    """Straights joined by circular arcs: radii[i] is the arc at corner pts[i + 1], shrunk where the legs
    are too short. Returns dense (x, z) points along the track."""
    out = [pts[0]]
    n = len(pts)
    for i in range(1, n - 1):
        (ax, az), (bx, bz), (cx, cz) = pts[i - 1], pts[i], pts[i + 1]
        l0, l1 = math.hypot(bx - ax, bz - az), math.hypot(cx - bx, cz - bz)
        d0, d1 = ((bx - ax) / l0, (bz - az) / l0), ((cx - bx) / l1, (cz - bz) / l1)
        turn = math.atan2(d0[0] * d1[1] - d0[1] * d1[0], d0[0] * d1[0] + d0[1] * d1[1])
        if abs(turn) < 1e-3:
            out.append((bx, bz))
            continue
        half = math.tan(abs(turn) / 2)
        t = min(radii[i - 1] * half, l0 if i == 1 else l0 / 2, l1 if i == n - 2 else l1 / 2)
        r = t / half
        sg = 1 if turn > 0 else -1
        a = (bx - d0[0] * t, bz - d0[1] * t)
        c = (a[0] - d0[1] * sg * r, a[1] + d0[0] * sg * r)
        a0 = math.atan2(a[1] - c[1], a[0] - c[0])
        k = max(2, int(abs(turn) * r / step) + 1)
        out += [(c[0] + r * math.cos(a0 + turn * j / k), c[1] + r * math.sin(a0 + turn * j / k)) for j in range(k + 1)]
    out.append(pts[-1])
    dense = [out[0]]
    for p in out[1:]:
        if math.hypot(p[0] - dense[-1][0], p[1] - dense[-1][1]) > 1e-3:
            dense.append(p)
    return dense


def ribbon(b, mat, pts, width, y, offset=0.0):
    """A flat strip along dense points (a track bed, a rail), offset sideways from the centre line."""
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


def seg_dist(px, pz, a, c):
    dx, dz = c[0] - a[0], c[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (pz - a[1]) * dz) / ((dx * dx + dz * dz) or 1.0)))
    return math.hypot(px - a[0] - dx * t, pz - a[1] - dz * t)


def preview_yard(b, parsed, s, keep_out):
    """Ground, curved track and trolley wires as the game will draw them - previews only. keep_out:
    rectangles (x0, z0, x1, z1) of the buildings, where no wire pole may stand."""
    x0, z0, x1, z1 = L.bounds(parsed)
    K.slab(b, GROUND, x0 - 14, z0 - 14, x1 + 14, z1 + 14, -0.6, 0.0)
    tracks = [fillet(p, r) for p, r in track_plan(parsed, s)]
    segs = [(a, c) for t in tracks for a, c in zip(t, t[1:])]
    for t in tracks:
        ribbon(b, CONC, t, GAUGE + 1.0, 0.02)
        for o in (-GAUGE / 2, GAUGE / 2):
            ribbon(b, METAL, t, 0.09, 0.05, offset=o)
    for a, c in segs:
        b.rod(DARK, (a[0], WIRE_Y, a[1]), (c[0], WIRE_Y, c[1]), 0.025, segs=3)
    poles = []
    for t in tracks:                             # a pole about every 20 m, beside the track, clear of the rest
        walk = []
        for a, c in zip(t, t[1:]):
            n = max(1, int(math.hypot(c[0] - a[0], c[1] - a[1]) / 2.0))
            walk += [(a[0] + (c[0] - a[0]) * k / n, a[1] + (c[1] - a[1]) * k / n, c[0] - a[0], c[1] - a[1]) for k in range(n)]
        run = 10.0
        for wx, wz, dx, dz in walk:
            run += 2.0
            if run < 20.0:
                continue
            ln = math.hypot(dx, dz) or 1.0
            for side in (2.4, -2.4):
                px, pz = wx - dz / ln * side, wz + dx / ln * side
                if (x0 + 0.5 < px < x1 - 0.5 and z0 + 0.5 < pz < z1 - 0.5
                        and not any(r[0] - 0.8 < px < r[2] + 0.8 and r[1] - 0.8 < pz < r[3] + 0.8 for r in keep_out)
                        and all(seg_dist(px, pz, a, c) > 1.9 for a, c in segs)
                        and all(math.hypot(px - mx, pz - mz) > 12.0 for mx, mz in poles)):
                    poles.append((px, pz))
                    b.cyl(GREY, (px, 0, pz), 0.16, WIRE_Y + 1.0, segs=8, r2=0.11)
                    b.rod(GREY, (px, WIRE_Y + 0.5, pz), (wx, WIRE_Y + 0.1, wz), 0.05, segs=4)
                    run = 0.0
                    break


# ------------------------------------------------------------------ model --

def shed(b, x0, z0, x1, z1, lanes_z, h=8.4):
    """The tram shed: brick long walls, open portals over each lane at both ends, gable roof and lantern.
    No floor, rails or wires - the game draws the track and the trolley wire through it."""
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
        K.slab(b, BRICK, xe - pier, z0, xe + pier, z1, 5.6, h)             # lintel over the portals (wire at 5.8 inside)
        for lz in lanes_z:                                               # arched heads, rendered as brick arcs
            for k in range(5):
                a = math.pi * (k + 0.5) / 5
                K.slab(b, CONC, xe - pier - 0.05, lz - 1.85 * math.cos(a) - 0.25, xe + pier + 0.05,
                       lz - 1.85 * math.cos(a) + 0.25, 5.1 + 0.5 * math.sin(a), 5.6)
    W = z1 - z0
    ridge = W * 0.22
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
    """Two-storey dispatch office against the shed, sign and star facing the front track."""
    top = K.block(b, x0, z0, x1, z1, 2, wall=STUCCO, roof=ROOF)
    K.slab(b, CONC, x0 - 0.2, z1, x1 + 0.2, z1 + 0.3, 0, 0.9)
    K.door(b, (x0 + x1) / 2, z1 + 0.15, 2.4, 2.8)
    K.sign(b, 'ТРАМГРУЗ', ((x0 + x1) / 2, top + 1.0, z1 + 0.2), 1.5, board=(x1 - x0 - 2.0, 2.1, WHITE))
    K.star(b, ((x0 + x1) / 2, top + 3.4, z1 + 0.15), 1.0)
    for x in (x0 + 1.5, x1 - 1.5):
        b.box(GLOW, (x, 3.0, z1 + 0.2), (0.4, 0.4, 0.1))
    return top


def substation(b, x0, z0, x1, z1):
    """Traction substation, the trolley wires' feed: a brick block lengthwise in z, door to the west."""
    top = K.block(b, x0, z0, x1, z1, 1, wall=BRICK, roof=ROOF, floor_h=4.2, base=FOOT)
    K.slab(b, GREY, x0 - 0.12, (z0 + z1) / 2 - 0.9, x0, (z0 + z1) / 2 + 0.9, 0, 2.6)       # door
    b.box(HAZARD, (x0 - 0.13, 3.2, z1 - 1.3), (0.04, 0.7, 0.7))
    for k in range(3):                                                   # transformers on the roof
        b.box(GREY, ((x0 + x1) / 2, top + 0.4, z0 + 1.4 + k * (z1 - z0 - 2.8) / 2), (1.6, 0.8, 1.2))
    return top


def sand_tower(b, sx, sz):
    """The depot's sand tower, its chute reaching east over the track."""
    for dx, dz in ((-1.1, -1.1), (1.1, -1.1), (1.1, 1.1), (-1.1, 1.1)):
        b.rod(GREY, (sx + dx, FOOT, sz + dz), (sx + dx * 0.8, 6.0, sz + dz * 0.8), 0.12, segs=5)
    b.cyl(CORR, (sx, 6.0, sz), 1.6, 4.2, segs=14)
    b.cyl(ROOF, (sx, 10.2, sz), 1.75, 0.9, segs=14, r2=0.3)
    b.rod(METAL, (sx + 1.2, 7.0, sz), (sx + 3.0, 5.8, sz), 0.12, segs=6)


def yard(b, key, lines, parsed):
    """The buildings, placed in what the game's tracks leave free (see track_plan): the shed over the
    parking lanes, the dispatch wing between the shed and the station track, the substation in the
    south-east corner beyond the exit spine, the sand tower and a lamp mast in the south-west corner
    beyond the west spine. Returns the building rectangles (x0, z0, x1, z1)."""
    x0, z0, x1, z1 = L.bounds(parsed)
    lanes = lane_lines(parsed)
    lanes_z = [z for z, _w, _e in lanes]
    sx0, sx1 = min(w for _z, w, _e in lanes) - 1.6, max(e for _z, _w, e in lanes) + 1.6
    sz0, sz1 = min(lanes_z) - 2.0, max(lanes_z) + 2.1
    roof = shed(b, sx0, sz0, sx1, sz1, lanes_z)
    span = sx1 - sx0
    dx0, dz0, dx1, dz1 = -span * 0.24, sz1 + 0.25, span * 0.24, sz1 + 4.9
    dispatch(b, dx0, dz0, dx1, dz1)
    ss = (x1 - 5.0, z0 + 0.6, x1 - 0.6, z0 + 7.6)
    substation(b, *ss)
    sand = (x0 + 2.4, z0 + 3.6)
    sand_tower(b, *sand)
    lamps = ((x0 + 1.6, z0 + 10.0), (x1 - 2.8, z0 + 10.2))
    for x, z in lamps:
        K.lamp_mast(b, x, z, h=14.0, head=2.0)
    K.fence(b, x0 + 0.4, z0 + 0.15, sx0 - 0.6, z0 + 0.15, h=2.0)
    K.fence(b, sx1 + 0.6, z0 + 0.15, ss[0] - 0.4, z0 + 0.15, h=2.0)
    flag = (dx0 - 2.0, sz1 + 3.0)
    K.flagpole(b, *flag, h=10.0)
    # below ground, out of sight: stretches the model's box over the whole footprint, as the
    # game's depot model does with a strip along its front edge
    K.slab(b, DARK, x0, z1 - 0.3, x1, z1, -1.2, -0.4)
    K.slab(b, DARK, x0, z0, x1, z0 + 0.3, -1.2, -0.4)
    b.fire += [((sx0 + sx1) / 2, roof - 1.0, (sz0 + sz1) / 2), (0.0, 7.5, sz1 + 2.5)]
    return ([(sx0, sz0, sx1, sz1), (dx0 - 0.3, sz1, dx1 + 0.3, dz1 + 0.4), ss, (sand[0] - 1.9, sand[1] - 1.9, sand[0] + 1.9, sand[1] + 1.9),
             (flag[0] - 0.3, flag[1] - 0.3, flag[0] + 0.3, flag[1] + 0.3)]
            + [(x - 0.8, z - 0.8, x + 0.8, z + 0.8) for x, z in lamps])


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


# Construction: fixed amounts per phase, not $COST_RESOURCE_AUTO. AUTO scales with the model, and
# with the below-ground strips that stretch it over the whole yard it asked ~1300 t of concrete; the
# game's train office costs 2791 workdays, 81 t concrete, 62 gravel, 49 asphalt, 159 bricks,
# 53 boards, 19 steel. The small yard costs less than that, the large one (COST_SCALE) about as much.
# Each phase: (work type, construction stops (x, z, x, z) from the game's tram depot, resources).
COSTS = [
    ('SOVIET_CONSTRUCTION_GROUNDWORKS 0.0', [(13.5, 1.1, 15.0, 0.8), (-23.6, 0.8, -24.9, 1.5)],
     [('workers', 600), ('concrete', 50), ('gravel', 45), ('asphalt', 30)]),
    ('SOVIET_CONSTRUCTION_BRICKS_LAYING 1.0', [(13.5, 1.1, 15.0, 0.8), (-23.6, 0.8, -24.9, 1.5),
                                              (-29.5, -15.0, -31.0, -15.1), (25.5, -13.8, 26.9, -14.3)],
     [('workers', 1200), ('bricks', 110), ('boards', 35)]),
    ('SOVIET_CONSTRUCTION_STEEL_LAYING 1.0', [(-27.5, 1.0, -26.0, 1.0), (25.5, -13.8, 26.9, -14.3)],
     [('workers', 400), ('steel', 14)]),
]
COST_SCALE = {'tramdo_small': 1.0, 'tramdo_large': 1.25}


def building_ini(key, lines):
    scale, name, _limit = L.SIZES[key]
    out = ['$NAME_STR "%s"' % name, '$TYPE_DISTRIBUTION_OFFICE', '$SUBTYPE_TRAM',
           '$MENU_SFX building_tram_depot', '$WORKING_VEHICLES_NEEDED %d' % VEHICLES[key], '']
    out += lines + ['']
    k = COST_SCALE[key]
    for work, stops, resources in COSTS:
        out += ['------------------', '$COST_WORK ' + work, '$COST_WORK_BUILDING_ALL']
        out += ['$COST_WORK_VEHICLE_STATION %.2f 0.0 %.2f %.2f 0.0 %.2f' % (x0 * scale, z0, x1 * scale, z1) for x0, z0, x1, z1 in stops]
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
    for key, (scale, name, _limit) in L.SIZES.items():
        lines, parsed = L.geometry(scale)
        b = K.builder(seed=sum(map(ord, key)))
        keep_out = yard(b, key, lines, parsed)
        shapes, used = b.export_shapes(prefix='td_')
        used_all.update(used)
        model = nmf.Model(); model.materials = used; model.shapes = shapes
        adir = os.path.join(ITEMDIR, key)
        os.makedirs(adir, exist_ok=True)
        nmf.write(model, os.path.join(adir, 'model.nmf'))
        bbox = mmkit.model_bbox(shapes)
        mmkit.write_bbox_file(os.path.join(adir, 'building.bbox'), shapes)
        mmkit.write_fire_file(os.path.join(adir, 'building.fire'), b.fire)
        mmkit.write_text(os.path.join(adir, 'building.ini'), building_ini(key, lines))
        mmkit.write_text(os.path.join(adir, 'renderconfig.ini'), RENDERCONFIG % {'n': key})
        mmkit.write_text(os.path.join(matdir, key + '.mtl'), mtl(used))
        mmkit.write_text(os.path.join(matdir, key + '_e.mtl'), mtl(used, emissive=True))
        pb = K.builder(seed=1)                   # ground and track as the game draws them: previews only
        preview_yard(pb, parsed, scale, keep_out)
        pb.export_shapes()                       # triangulates and maps; the shapes themselves are dropped
        obs = b.preview_objects(bmats, key) + pb.preview_objects(bmats, key + '_yard')
        pos, tgt = mmkit.frame_camera(bbox, azimuth_deg=-35, elevation_deg=32, fill=0.9)
        mmkit.render(os.path.join(PREVIEW, key + '.png'), pos, tgt, (1400, 900), samples=32)
        pos, tgt = mmkit.frame_camera(bbox, azimuth_deg=-30, elevation_deg=40, fill=0.95)
        mmkit.render(os.path.join(PREVIEW, key + '_icon.png'), pos, tgt, (384, 384), transparent=True, samples=24)
        mmkit.save_scaled_png(os.path.join(PREVIEW, key + '_icon.png'), os.path.join(adir, 'imagegui.png'), 96, 96)
        pos, tgt = mmkit.frame_camera(bbox, azimuth_deg=-35, elevation_deg=30, fill=0.8)      # poster cut-out
        mmkit.render(os.path.join(PREVIEW, key + '_cut.png'), pos, tgt, (1800, 1200), transparent=True, samples=32)
        top = mmkit.frame_camera(bbox, azimuth_deg=180, elevation_deg=89.5, fill=1.0)     # plan view, north up
        mmkit.render(os.path.join(PREVIEW, key + '_top.png'), top[0], top[1], (1400, 560), samples=16,
                     ortho=bbox[3] - bbox[0] + 10)
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
