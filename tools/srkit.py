"""Space Race kit: Blender-side composites on top of mmkit.Builder.

Palette and tile sizes come from space_textures.py so geometry and textures
agree. Coordinates are GAME coordinates (x right, y up, z forward / road side);
mmkit converts on placement. Real dimensions are used throughout (metres).

Rockets are built standing on their base at the origin, +y up. Reference
figures (see docs/space-race-design.md):
    R-7 / Vostok-K 38.4 m, core 2.95 m, strap-ons 19 m x 2.68 m, span 10.3 m
    Soyuz 11A511   49.5 m
    Proton UR-500K 44.3 m to the shroud tip, core 4.1 m, six 1.6 m outboard tanks
    N1             105.3 m, base 17 m, 30 NK-15 engines
"""
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import mmkit  # noqa: E402
from mmkit import G, rot  # noqa: E402
from space_palette import TILE, MATS, EMISSIVE  # noqa: E402

(CONC, SCORCH, WHITE, GREY, GREEN, RED, STRIPES, GLASS, STUCCO, BRICK, ROOF, ASPH, GROUND, METAL, DARK,
 GLOW, CORR, HAZARD, TITAN, FROST, BLUE) = range(len(MATS))
assert MATS[BLUE] == 'sr_blue'


def builder(seed=1):
    return mmkit.Builder(seed=seed, mats=MATS, tile=TILE)


def place(dst, fn, center=(0, 0, 0), yaw=0.0, pitch=0.0, roll=0.0, **kw):
    """Build fn(tmp_builder, **kw) around the origin, then merge it into dst
    rotated and moved - for rockets lying on transporters, tilted parts."""
    import bpy
    tmp = builder(seed=7)
    out = fn(tmp, **kw)
    M = Matrix.Translation(G(*center)) @ rot(pitch, yaw, roll)
    for mi in range(len(MATS)):
        bm = tmp.master[mi]
        if not bm.faces:
            continue
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts[:])
        me = bpy.data.meshes.new('srkit_place')
        bm.to_mesh(me)
        dst.master[mi].from_mesh(me)
        bpy.data.meshes.remove(me)
    tmp.free()
    return out


# ------------------------------------------------------------------ basics --

LOT_TOP = 0.10   # the ground plate's top while building a model; space_scene lifts the finished model by LIFT
LOT_SKIRT = 2.6  # the plate reaches this far below LOT_TOP, so it never floats over lower ground


def lot(b, mat, w, d, cx=0.0, cz=0.0):
    b.box(mat, (cx, LOT_TOP - LOT_SKIRT / 2, cz), (w, LOT_SKIRT, d))


def slab(b, mat, x0, z0, x1, z1, y0, y1, yaw=0.0):
    """Axis box by extents (before yaw about its own centre)."""
    b.box(mat, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), yaw=yaw)


def sphere(b, mat, center, r, segs=16, rings=10):
    bm = b.master[mat]
    ret = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r,
                                    matrix=Matrix.Translation(G(*center)))
    b._finish(bm, ret, mat, True)


def dome(b, mat, center, r, h=None, segs=16, rings=5):
    """Upper half of an ellipsoid (radius r, height h) sitting on center."""
    h = r if h is None else h
    bm = b.master[mat]
    rows = []
    for j in range(rings + 1):
        a = (math.pi / 2) * j / rings
        rr = r * math.cos(a)
        yy = h * math.sin(a)
        if j == rings:
            rows.append([bm.verts.new(G(center[0], center[1] + h, center[2]))])
            break
        rows.append([bm.verts.new(G(center[0] + rr * math.cos(2 * math.pi * i / segs), center[1] + yy,
                                    center[2] + rr * math.sin(2 * math.pi * i / segs))) for i in range(segs)])
    faces = []
    for j in range(rings):
        lo, hi = rows[j], rows[j + 1]
        for i in range(segs):
            if len(hi) == 1:
                faces.append(bm.faces.new((lo[i], lo[(i + 1) % segs], hi[0])))
            else:
                faces.append(bm.faces.new((lo[i], lo[(i + 1) % segs], hi[(i + 1) % segs], hi[i])))
    for f in faces:
        f.material_index = mat
        f.smooth = True
    # the faces were wound for +y outward normals when viewed from outside
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def ngon_prism(b, mat, pts2d, y0, y1, center=(0, 0, 0), yaw=0.0, pitch=0.0):
    """Extrude a 2D outline (local x, z) from y0 to y1 - stars, odd plans."""
    bm = b.master[mat]
    M = Matrix.Translation(G(*center)) @ rot(pitch, yaw, 0)
    lo = [bm.verts.new(M @ G(x, y0, z)) for x, z in pts2d]
    hi = [bm.verts.new(M @ G(x, y1, z)) for x, z in pts2d]
    faces = [bm.faces.new(lo[::-1]), bm.faces.new(hi)]
    n = len(pts2d)
    for i in range(n):
        faces.append(bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i])))
    for f in faces:
        f.material_index = mat
        f.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def wedge(b, mat, x0, x1, h, z0, z1):
    """An embankment rising from height 0 at x0 to h at x1, spanning z0..z1."""
    ngon_prism(b, mat, [(x0, 0.0), (x1, 0.0), (x1, h)], -(z1 - z0) / 2, (z1 - z0) / 2, center=(0, 0, (z0 + z1) / 2), pitch=-90)


def star(b, center, r, depth=0.3, yaw=0.0, mat=RED, upright=True):
    """Five-pointed Soviet star. upright=True stands it facing +z (a sign);
    otherwise it lies flat."""
    pts = []
    for k in range(10):
        a = math.radians(90 + k * 36)
        rr = r if k % 2 == 0 else r * 0.40
        pts.append((rr * math.cos(a), -rr * math.sin(a)))
    if upright:
        ngon_prism(b, mat, pts, -depth / 2, depth / 2, center=center, yaw=yaw, pitch=90)
    else:
        ngon_prism(b, mat, pts, 0, depth, center=center, yaw=yaw)


def lamp_mast(b, x, z, h=24.0, head=3.0):
    """Floodlight tower: lattice-ish pole and a bank of lights on top."""
    for dx, dz in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
        b.rod(GREY, (x + dx, 0, z + dz), (x + dx * 0.35, h, z + dz * 0.35), 0.1, segs=5)
    for k in range(1, int(h / 3)):
        y = k * 3.0
        s = 0.5 - 0.325 * y / h
        b.beam(GREY, (x - s, y, z - s), (x + s, y + 1.5, z + s), 0.06)
    slab(b, GREY, x - head / 2, z - 0.8, x + head / 2, z + 0.8, h, h + 0.3)
    for k in range(4):
        b.box(DARK, (x - head / 2 + 0.4 + k * (head - 0.8) / 3, h + 0.9, z + 0.3), (0.6, 0.9, 0.35), pitch=-20)
        b.box(GLOW, (x - head / 2 + 0.4 + k * (head - 0.8) / 3, h + 0.8, z + 0.52), (0.5, 0.7, 0.05), pitch=-20)


def flagpole(b, x, z, h=12.0):
    b.rod(METAL, (x, 0, z), (x, h, z), 0.1, segs=6)
    b.box(RED, (x + 1.6, h - 1.1, z), (3.2, 2.0, 0.04))


# --------------------------------------------------------------- lattices --

def lattice_column(b, mat, base, w0, w1, h, levels=None, beam=0.25, yaw=0.0, diag=True, legs_mat=None):
    """Four-legged tapering lattice tower (square plan w0 at the base, w1 at the top)."""
    x, y, z = base
    levels = levels or max(2, int(h / 4.5))
    M = rot(0, yaw, 0)

    def P(sx, sz, t):
        w = (w0 + (w1 - w0) * t) / 2
        o = M @ Vector((sx * w, -sz * w, 0))
        return (x + o.x, y + t * h, z - o.y)
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    lm = legs_mat if legs_mat is not None else mat
    for sx, sz in corners:
        b.beam(lm, P(sx, sz, 0), P(sx, sz, 1), beam * 1.6)
    for k in range(1, levels + 1):
        t0, t1 = (k - 1) / levels, k / levels
        for i in range(4):
            a, c = corners[i], corners[(i + 1) % 4]
            b.beam(mat, P(a[0], a[1], t1), P(c[0], c[1], t1), beam)
            if diag:
                if k % 2:
                    b.beam(mat, P(a[0], a[1], t0), P(c[0], c[1], t1), beam * 0.8)
                else:
                    b.beam(mat, P(c[0], c[1], t0), P(a[0], a[1], t1), beam * 0.8)


def lattice_girder(b, mat, p0, p1, w, h, n=None, beam=0.2):
    """Box truss from p0 to p1 (a horizontal-ish girder), w wide, h deep."""
    a, c = Vector(p0), Vector(p1)
    d = c - a
    L = d.length
    n = n or max(2, int(L / max(w, h)))
    fwd = d.normalized()
    side = fwd.cross(Vector((0, 1, 0)))
    if side.length < 1e-3:
        side = Vector((1, 0, 0))
    side.normalize()
    up = side.cross(fwd).normalized()
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        off = side * (sx * w / 2) + up * (sy * h / 2)
        pts.append(off)
    for off in pts:
        b.beam(mat, tuple(a + off), tuple(c + off), beam * 1.4)
    for k in range(n + 1):
        t = k / n
        q = a + d * t
        for i in range(4):
            b.beam(mat, tuple(q + pts[i]), tuple(q + pts[(i + 1) % 4]), beam)
        if k < n:
            q2 = a + d * ((k + 1) / n)
            for i in range(4):
                if (k + i) % 2 == 0:
                    b.beam(mat, tuple(q + pts[i]), tuple(q2 + pts[(i + 1) % 4]), beam * 0.8)


# ------------------------------------------------------------------ tanks --

def tank_h(b, mat, center, r, length, yaw=0.0, saddles=True):
    """Horizontal cylindrical tank with shallow conical heads, on concrete saddles."""
    x, y, z = center
    M = rot(0, yaw, 0)
    ax = M @ Vector((1, 0, 0))
    a = (x - ax.x * length / 2, y, z + ax.y * length / 2)
    b_ = (x + ax.x * length / 2, y, z - ax.y * length / 2)
    b.rod(mat, a, b_, r, segs=14)
    for p, sgn in ((a, -1), (b_, 1)):
        tip = (p[0] + sgn * ax.x * r * 0.45, p[1], p[2] - sgn * ax.y * r * 0.45)
        b.spike(mat, p, (tip[0] - p[0], 0, tip[2] - p[2]), r * 0.45, radius=r, segs=14)
    if saddles:
        for t in (-0.32, 0.32):
            cx, cz = x + ax.x * length * t, z - ax.y * length * t
            b.box(CONC, (cx, (y - r) / 2 + 0.2, cz), (0.8, max(0.4, y - r + 0.6), r * 1.6), yaw=yaw)


def tank_v(b, mat, base, r, h, roof=True, ladder=True):
    x, y, z = base
    b.cyl(mat, (x, y, z), r, h, segs=18)
    if roof:
        b.cyl(mat, (x, y + h, z), r, r * 0.25, segs=18, r2=r * 0.15)
    if ladder:
        b.rod(DARK, (x + r + 0.3, y, z), (x + r + 0.3, y + h, z), 0.05, segs=4)
        b.rod(DARK, (x + r + 0.3, y, z + 0.5), (x + r + 0.3, y + h, z + 0.5), 0.05, segs=4)


def sphere_tank(b, mat, center, r, legs=8):
    x, y, z = center
    sphere(b, mat, center, r, segs=18, rings=12)
    for k in range(legs):
        a = 2 * math.pi * k / legs
        px, pz = x + r * 0.9 * math.cos(a), z + r * 0.9 * math.sin(a)
        b.rod(GREY, (px, 0, pz), (px, y, pz), 0.18, segs=6)
    b.torus(GREY, (x, y * 0.45, z), r * 0.9, 0.08, segs=18, rings=4)


def pipe(b, mat, pts, r=0.25):
    for p0, p1 in zip(pts, pts[1:]):
        b.rod(mat, p0, p1, r, segs=8)


def pipe_rack(b, x0, z0, x1, z1, h=5.0, n=4, span=6.0):
    L = math.hypot(x1 - x0, z1 - z0)
    k = max(1, int(L / span))
    ux, uz = (x1 - x0) / L, (z1 - z0) / L
    nx, nz = -uz, ux
    for i in range(k + 1):
        cx, cz = x0 + ux * L * i / k, z0 + uz * L * i / k
        for s in (-1, 1):
            b.rod(GREY, (cx + nx * s * 1.2, 0, cz + nz * s * 1.2), (cx + nx * s * 1.2, h, cz + nz * s * 1.2), 0.14, segs=5)
        b.beam(GREY, (cx - nx * 1.4, h, cz - nz * 1.4), (cx + nx * 1.4, h, cz + nz * 1.4), 0.25)
    for j in range(n):
        o = -0.9 + 1.8 * j / max(1, n - 1)
        mat = [METAL, GREY, FROST, RED][j % 4]
        b.rod(mat, (x0 + nx * o, h + 0.35, z0 + nz * o), (x1 + nx * o, h + 0.35, z1 + nz * o), 0.18, segs=8)


# ------------------------------------------------------------------ dishes --

def dish(b, center, D, elev=45.0, az=0.0, depth=0.14, mat=WHITE, segs=24, rings=5, feed=True):
    """Parabolic reflector with a quadripod feed. center is the dish vertex;
    elev tilts the boresight up from horizontal, az turns it about y."""
    R_ = D / 2.0
    bm = b.master[mat]
    M = Matrix.Translation(G(*center)) @ rot(0, az, 0) @ Matrix.Rotation(math.radians(90 - elev), 4, 'X')
    # local frame: boresight along blender +Z before rotation (= game up), then tilted
    rows = [[bm.verts.new(M @ Vector((0, 0, 0)))]]
    for j in range(1, rings + 1):
        rr = R_ * j / rings
        zz = depth * D * (rr / R_) ** 2
        rows.append([bm.verts.new(M @ Vector((rr * math.cos(2 * math.pi * i / segs), rr * math.sin(2 * math.pi * i / segs), zz)))
                     for i in range(segs)])
    faces = []
    for j in range(rings):
        lo, hi = rows[j], rows[j + 1]
        for i in range(segs):
            if len(lo) == 1:
                faces.append(bm.faces.new((lo[0], hi[i], hi[(i + 1) % segs])))
            else:
                faces.append(bm.faces.new((lo[i], hi[i], hi[(i + 1) % segs], lo[(i + 1) % segs])))
    # back side (so the dish is visible from behind with a slight thickness)
    back = []
    for j in range(rings + 1):
        back.append([bm.verts.new(v.co - (M.to_3x3() @ Vector((0, 0, 0.25)))) for v in rows[j]])
    for j in range(rings):
        lo, hi = back[j], back[j + 1]
        for i in range(segs):
            if len(lo) == 1:
                faces.append(bm.faces.new((lo[0], hi[(i + 1) % segs], hi[i])))
            else:
                faces.append(bm.faces.new((lo[i], lo[(i + 1) % segs], hi[(i + 1) % segs], hi[i])))
    for f in faces:
        f.material_index = mat
        f.smooth = True
    if feed:
        focus = M @ Vector((0, 0, D * 0.42))
        fg = (focus.x, focus.z, -focus.y)
        for i in range(4):
            a = 2 * math.pi * i / 4 + math.pi / 4
            rim = M @ Vector((R_ * 0.9 * math.cos(a), R_ * 0.9 * math.sin(a), depth * D * 0.81))
            b.rod(GREY, (rim.x, rim.z, -rim.y), fg, D * 0.008 + 0.04, segs=4)
        b.box(DARK, fg, (D * 0.05 + 0.3, D * 0.05 + 0.3, D * 0.05 + 0.3))
    return center


# --------------------------------------------------------------- buildings --

def block(b, x0, z0, x1, z1, floors, wall=GLASS, roof=ROOF, floor_h=3.6, base=0.0, parapet=0.9, trim=CONC):
    """A flat-roofed block whose walls use a facade texture. floor_h must match
    the facade tile (3.6 m per floor) so windows land on floors."""
    h = floors * floor_h
    slab(b, wall, x0, z0, x1, z1, base, base + h)
    slab(b, roof, x0 + 0.05, z0 + 0.05, x1 - 0.05, z1 - 0.05, base + h, base + h + 0.25)
    if parapet:
        for (a0, c0, a1, c1) in ((x0, z0, x1, z0 + 0.3), (x0, z1 - 0.3, x1, z1), (x0, z0, x0 + 0.3, z1), (x1 - 0.3, z0, x1, z1)):
            slab(b, trim, a0, c0, a1, c1, base + h, base + h + parapet)
    slab(b, trim, x0 - 0.1, z0 - 0.1, x1 + 0.1, z1 + 0.1, base - 0.3, base + 0.6)
    return base + h


def hall(b, x0, z0, x1, z1, h, wall=CORR, roof=ROOF, kind='gable', ridge=None, band=True, plinth=BRICK, axis='x'):
    """Industrial hall. kind: gable | flat | sawtooth | barrel. axis = ridge direction."""
    slab(b, plinth, x0, z0, x1, z1, 0, 1.8)
    slab(b, wall, x0 + 0.05, z0 + 0.05, x1 - 0.05, z1 - 0.05, 1.8, h)
    if band:
        k = int((h - 1.0) / 3.6) - 1
        if k >= 1:
            y0, y1 = k * 3.6, (k + 1) * 3.6
            for (a0, c0, a1, c1) in ((x0 - 0.06, z0 - 0.06, x1 + 0.06, z0 + 0.1), (x0 - 0.06, z1 - 0.1, x1 + 0.06, z1 + 0.06),
                                     (x0 - 0.06, z0, x0 + 0.1, z1), (x1 - 0.1, z0, x1 + 0.06, z1)):
                slab(b, GLASS, a0, c0, a1, c1, y0, y1)
    W = (x1 - x0) if axis == 'z' else (z1 - z0)
    ridge = ridge if ridge is not None else W * 0.18
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    L = (z1 - z0) if axis == 'z' else (x1 - x0)
    yaw = 90 if axis == 'z' else 0
    if kind == 'flat':
        slab(b, roof, x0 - 0.2, z0 - 0.2, x1 + 0.2, z1 + 0.2, h, h + 0.4)
    elif kind == 'gable':
        ang = math.degrees(math.atan2(ridge, W / 2))
        half = math.hypot(W / 2, ridge) + 0.4
        for s in (-1, 1):
            off = s * W / 4
            if axis == 'x':
                b.box(roof, (cx, h + ridge / 2, cz + off), (L + 0.6, 0.3, half), pitch=s * ang)
            else:
                b.box(roof, (cx + off, h + ridge / 2, cz), (half, 0.3, L + 0.6), roll=-s * ang)
        # gable ends
        for e in (-1, 1):
            if axis == 'x':
                ex = cx + e * L / 2
                ngon_prism(b, wall, [(-W / 2, 0), (W / 2, 0), (0, ridge)], -0.15, 0.15, center=(ex, h, cz), yaw=90, pitch=-90)
            else:
                ez = cz + e * L / 2
                ngon_prism(b, wall, [(-W / 2, 0), (W / 2, 0), (0, ridge)], -0.15, 0.15, center=(cx, h, ez), pitch=-90)
    elif kind == 'sawtooth':
        n = max(2, int(L / 9.0))
        step = L / n
        for i in range(n):
            t = -L / 2 + step * (i + 0.5)
            if axis == 'x':
                b.box(roof, (cx + t - step * 0.12, h + 1.8, cz), (step * 0.8, 0.3, W + 0.4), roll=22)
                slab(b, GLASS, cx + t + step * 0.36, z0, cx + t + step * 0.4, z1, h, h + 3.6)
            else:
                b.box(roof, (cx, h + 1.8, cz + t - step * 0.12), (W + 0.4, 0.3, step * 0.8), pitch=-22)
                slab(b, GLASS, x0, cz + t + step * 0.36, x1, cz + t + step * 0.4, h, h + 3.6)
        slab(b, roof, x0 - 0.2, z0 - 0.2, x1 + 0.2, z1 + 0.2, h, h + 0.3)
    elif kind == 'barrel':
        segs = 10
        for i in range(segs):
            a0 = math.pi * i / segs
            a1 = math.pi * (i + 1) / segs
            p0 = (W / 2 * math.cos(a0), ridge * math.sin(a0))
            p1 = (W / 2 * math.cos(a1), ridge * math.sin(a1))
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            wlen = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) + 0.1
            ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            if axis == 'x':
                b.box(roof, (cx, h + mid[1], cz + mid[0]), (L + 0.4, 0.3, wlen), pitch=-ang)
            else:
                b.box(roof, (cx + mid[0], h + mid[1], cz), (wlen, 0.3, L + 0.4), roll=ang)
        for e in (-1, 1):
            pts = [(W / 2 * math.cos(math.pi * i / segs), ridge * math.sin(math.pi * i / segs)) for i in range(segs + 1)]
            if axis == 'x':
                ngon_prism(b, wall, [(-p[0], p[1]) for p in pts], -0.15, 0.15, center=(cx + e * L / 2, h, cz), yaw=90, pitch=-90)
            else:
                ngon_prism(b, wall, [(-p[0], p[1]) for p in pts], -0.15, 0.15, center=(cx, h, cz + e * L / 2), pitch=-90)


def door(b, x, z, w, h, facing='z', mat=GREY):
    """A big industrial door (slightly proud of a wall at x or z)."""
    if facing == 'z':
        b.box(mat, (x, h / 2, z), (w, h, 0.25))
        for k in range(1, int(h / 1.2)):
            b.box(DARK, (x, k * 1.2, z + 0.13), (w, 0.08, 0.04))
    else:
        b.box(mat, (x, h / 2, z), (0.25, h, w))
        for k in range(1, int(h / 1.2)):
            b.box(DARK, (x + 0.13, k * 1.2, z), (0.04, 0.08, w))


def rail_track(b, x0, z0, x1, z1, gauge=1.52, sleepers=True):
    """Russian broad gauge track with ballast, sleepers and two rails."""
    L = math.hypot(x1 - x0, z1 - z0)
    ux, uz = (x1 - x0) / L, (z1 - z0) / L
    nx, nz = -uz, ux
    yaw = math.degrees(math.atan2(-uz, ux))
    b.box(ASPH, ((x0 + x1) / 2, 0.15, (z0 + z1) / 2), (L, 0.3, 3.4), yaw=yaw)
    if sleepers:
        n = int(L / 1.8)
        for i in range(n):
            t = (i + 0.5) / n
            b.box(DARK, (x0 + ux * L * t, 0.36, z0 + uz * L * t), (0.25, 0.14, 2.6), yaw=yaw)
    for s in (-1, 1):
        o = s * gauge / 2
        b.box(METAL, ((x0 + x1) / 2 + nx * o, 0.52, (z0 + z1) / 2 + nz * o), (L, 0.16, 0.08), yaw=yaw)


def mtext(b, mat, body, pos, size, extrude, yaw=0.0):
    """Raised lettering built mirrored left-right: the engine shows every model mirrored
    (seen in game 2026-09-29: OKB-1 and PLUTON read backwards), so this reads correctly there."""
    import bpy
    cu = bpy.data.curves.new('sign', 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.resolution_u = 3
    cu.align_x = 'CENTER'
    ob = bpy.data.objects.new('sign', cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    M = Matrix.Translation(G(*pos)) @ rot(yaw=yaw) @ Matrix.Rotation(math.radians(90), 4, 'X') @ Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    bm = b.master[mat]
    vmap = {v.index: bm.verts.new(M @ v.co) for v in me.vertices}
    faces = []
    for p in me.polygons:
        try:
            f = bm.faces.new([vmap[i] for i in reversed(p.vertices)])
            f.material_index = mat
            f.smooth = False
            faces.append(f)
        except ValueError:
            pass
    ob.evaluated_get(dg).to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)


def sign(b, text, pos, size, yaw=0.0, board=None, depth=0.12):
    """Raised letters on an optional backing board (board = (w, h, mat))."""
    x, y, z = pos
    if board:
        w, h, mat = board
        b.box(mat, (x, y + size * 0.35, z - 0.1), (w, h, 0.15), yaw=yaw)
    mtext(b, RED, text, (x, y, z), size, depth, yaw=yaw)


def fence(b, x0, z0, x1, z1, h=2.4, step=4.0):
    L = math.hypot(x1 - x0, z1 - z0)
    n = max(1, int(L / step))
    for i in range(n + 1):
        t = i / n
        b.rod(GREY, (x0 + (x1 - x0) * t, 0, z0 + (z1 - z0) * t), (x0 + (x1 - x0) * t, h, z0 + (z1 - z0) * t), 0.05, segs=4)
    for y in (h * 0.35, h * 0.7, h):
        b.rod(METAL, (x0, y, z0), (x1, y, z1), 0.02, segs=3)


# ----------------------------------------------------------------- rockets --

def _stage(b, mat, y0, y1, r0, r1=None, x=0.0, z=0.0, segs=20):
    b.cyl(mat, (x, y0, z), r0, y1 - y0, segs=segs, r2=r0 if r1 is None else r1)


def _nozzles(b, x, y, z, n, ring, r, L, mat=DARK):
    for k in range(n):
        a = 2 * math.pi * k / n + math.pi / n
        px, pz = (x + ring * math.cos(a), z + ring * math.sin(a)) if ring > 0 else (x, z)
        b.cyl(mat, (px, y - L, pz), r, L, segs=10, r2=r * 0.55)


def rocket_r7(b, base=(0, 0, 0), variant='vostok', skin=GREY):
    """Semyorka family standing on its base. variant: sputnik | vostok | soyuz.
    Returns the total height."""
    x, y, z = base
    core_h = 27.8
    # Blok A (core): waisted - 2.95 m at the bottom tapering to 2.15 m, then the cylindrical top
    _stage(b, skin, y + 1.0, y + 17.0, 1.475, 1.2, x, z)
    _stage(b, skin, y + 17.0, y + core_h - 2.0, 1.2, 1.3, x, z)
    _stage(b, WHITE, y + core_h - 2.0, y + core_h, 1.3, 1.3, x, z)
    _nozzles(b, x, y + 1.0, z, 4, 0.65, 0.42, 1.8)
    # four strap-ons (Blok B, V, G, D): cones from a point near the core's upper third
    for k in range(4):
        a = math.radians(45 + 90 * k)
        cx, cz = x + 1.95 * math.cos(a), z + 1.95 * math.sin(a)
        b.cyl(skin, (cx, y + 1.0, cz), 1.34, 15.0, segs=16, r2=0.62)
        b.cyl(skin, (cx - 0.35 * math.cos(a), y + 16.0, cz - 0.35 * math.sin(a)), 0.62, 3.2, segs=14, r2=0.05)
        _nozzles(b, cx, y + 1.0, cz, 4, 0.55, 0.36, 1.6)
        # air rudder fins
        fx, fz = cx + 1.45 * math.cos(a), cz + 1.45 * math.sin(a)
        b.box(DARK, (fx, y + 1.6, fz), (0.1, 1.6, 0.9), yaw=-math.degrees(a))
    top = y + core_h
    if variant == 'sputnik':
        # 8K71PS: no third stage, a short conical nose over the satellite
        b.cyl(WHITE, (x, top, z), 1.3, 1.2, segs=20, r2=1.3)
        b.cyl(WHITE, (x, top + 1.2, z), 1.3, 2.6, segs=20, r2=0.25)
        return top + 3.8 - y
    # interstage truss + Blok E (Vostok) / Blok I (Soyuz)
    for k in range(8):
        a = 2 * math.pi * k / 8
        b.rod(DARK, (x + 1.2 * math.cos(a), top, z + 1.2 * math.sin(a)), (x + 1.25 * math.cos(a + 0.4), top + 1.1, z + 1.25 * math.sin(a + 0.4)), 0.06, segs=4)
    if variant == 'vostok':
        _stage(b, skin, top + 1.1, top + 3.9, 1.33, 1.33, x, z)
        _stage(b, WHITE, top + 3.9, top + 5.6, 1.33, 1.33, x, z)
        b.cyl(WHITE, (x, top + 5.6, z), 1.33, 4.4, segs=20, r2=0.35)   # payload shroud
        b.cyl(WHITE, (x, top + 10.0, z), 0.35, 0.6, segs=12, r2=0.05)
        return top + 10.6 - y
    # Soyuz: longer Blok I, bulged fairing, escape tower
    _stage(b, skin, top + 1.1, top + 7.8, 1.33, 1.33, x, z)
    _stage(b, WHITE, top + 7.8, top + 15.5, 1.5, 1.5, x, z)
    b.cyl(WHITE, (x, top + 15.5, z), 1.5, 2.8, segs=20, r2=0.6)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        b.box(GREY, (x + 1.55 * math.cos(a), top + 13.5, z + 1.55 * math.sin(a)), (0.15, 2.0, 0.9), yaw=-math.degrees(a))
    b.rod(DARK, (x, top + 18.3, z), (x, top + 21.5, z), 0.28, segs=10)
    b.cyl(DARK, (x, top + 21.5, z), 0.4, 0.8, segs=10, r2=0.05)
    return top + 22.3 - y


def rocket_proton(b, base=(0, 0, 0), skin=WHITE):
    """UR-500K: 4.1 m oxidiser core ringed by six 1.6 m fuel tanks, two upper stages, shroud."""
    x, y, z = base
    _stage(b, skin, y + 1.2, y + 21.0, 2.05, 2.05, x, z)
    for k in range(6):
        a = 2 * math.pi * k / 6
        cx, cz = x + 2.75 * math.cos(a), z + 2.75 * math.sin(a)
        _stage(b, GREY, y + 1.2, y + 18.8, 0.8, 0.8, cx, cz, segs=12)
        b.cyl(GREY, (cx, y + 18.8, cz), 0.8, 1.4, segs=12, r2=0.2)
        _nozzles(b, cx, y + 1.2, cz, 1, 0, 0.62, 1.6)
    _stage(b, skin, y + 21.0, y + 35.0, 2.07, 2.07, x, z)
    for k in range(12):
        a = 2 * math.pi * k / 12
        b.rod(DARK, (x + 2.0 * math.cos(a), y + 21.0, z + 2.0 * math.sin(a)), (x + 2.05 * math.cos(a + 0.3), y + 22.4, z + 2.05 * math.sin(a + 0.3)), 0.06, segs=4)
    _stage(b, GREY, y + 35.0, y + 41.5, 2.07, 2.07, x, z)
    _stage(b, skin, y + 41.5, y + 50.0, 2.07, 2.07, x, z)
    b.cyl(skin, (x, y + 50.0, z), 2.07, 3.0, segs=22, r2=0.7)
    return 53.0


def rocket_n1(b, base=(0, 0, 0), skin=WHITE):
    """N1-L3: a 105 m cone. Blok A with its 30 NK-15s, lattice interstages, Blok B,
    Blok V, then the L3 lunar complex under its shroud and the escape tower."""
    x, y, z = base
    # Blok A: 17 m at the base (the skirt), tanks inside
    b.cyl(skin, (x, y + 1.5, z), 8.5, 3.0, segs=32, r2=8.3)
    b.cyl(skin, (x, y + 4.5, z), 8.3, 25.5, segs=32, r2=5.4)
    for k in range(6):
        b.torus(GREY, (x, y + 6.0 + k * 4.4, z), 8.25 - k * 0.5, 0.12, segs=32, rings=4)
    _nozzles(b, x, y + 1.5, z, 24, 7.3, 0.55, 1.6)
    _nozzles(b, x, y + 1.5, z, 6, 2.6, 0.55, 1.6)
    # interstage lattice A/B
    top = y + 30.0
    for k in range(16):
        a = 2 * math.pi * k / 16
        b.rod(DARK, (x + 5.4 * math.cos(a), top, z + 5.4 * math.sin(a)), (x + 5.0 * math.cos(a + 0.2), top + 3.5, z + 5.0 * math.sin(a + 0.2)), 0.12, segs=4)
        b.rod(DARK, (x + 5.4 * math.cos(a), top, z + 5.4 * math.sin(a)), (x + 5.0 * math.cos(a - 0.2), top + 3.5, z + 5.0 * math.sin(a - 0.2)), 0.12, segs=4)
    b.cyl(DARK, (x, top + 0.5, z), 3.4, 2.5, segs=20, r2=3.0)     # Blok B engine bay inside the lattice
    # Blok B
    b.cyl(skin, (x, top + 3.5, z), 5.0, 17.0, segs=28, r2=3.8)
    b.torus(GREY, (x, top + 11.0, z), 4.45, 0.1, segs=28, rings=4)
    # interstage B/V lattice
    t2 = top + 20.5
    for k in range(12):
        a = 2 * math.pi * k / 12
        b.rod(DARK, (x + 3.8 * math.cos(a), t2, z + 3.8 * math.sin(a)), (x + 3.6 * math.cos(a + 0.25), t2 + 2.6, z + 3.6 * math.sin(a + 0.25)), 0.1, segs=4)
    b.cyl(DARK, (x, t2 + 0.3, z), 2.0, 2.0, segs=16, r2=1.8)
    # Blok V
    b.cyl(skin, (x, t2 + 2.6, z), 3.6, 11.5, segs=24, r2=3.0)
    # L3: Blok G and D, LOK/LK under the shroud, escape tower
    t3 = t2 + 14.1
    b.cyl(GREY, (x, t3, z), 3.0, 10.0, segs=24, r2=2.8)
    b.cyl(skin, (x, t3 + 10.0, z), 2.8, 18.0, segs=24, r2=2.2)
    b.cyl(skin, (x, t3 + 28.0, z), 2.2, 6.0, segs=24, r2=0.9)
    b.rod(DARK, (x, t3 + 34.0, z), (x, t3 + 39.0, z), 0.35, segs=10)
    b.cyl(DARK, (x, t3 + 39.0, z), 0.55, 1.2, segs=10, r2=0.05)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        b.box(GREY, (x + 2.3 * math.cos(a), t3 + 26.0, z + 2.3 * math.sin(a)), (0.2, 3.0, 1.4), yaw=-math.degrees(a))
    return t3 + 40.2 - y


def vostok_capsule(b, center, charred=False, instrument_module=True):
    """Vostok 3KA: the 2.3 m descent sphere on its bi-conical instrument module."""
    x, y, z = center
    skin = DARK if charred else METAL
    sphere(b, skin, (x, y + 1.15, z), 1.15, segs=16, rings=10)
    b.box(GLOW if not charred else DARK, (x + 0.55, y + 1.35, z + 0.9), (0.4, 0.4, 0.1))
    b.torus(GREY, (x, y + 1.15, z), 1.16, 0.05, segs=16, rings=4)
    if instrument_module:
        b.cyl(GREY, (x, y - 2.1, z), 1.2, 1.2, segs=16, r2=1.2)
        b.cyl(GREY, (x, y - 0.9, z), 1.2, 0.9, segs=16, r2=0.6)
        for k in range(8):
            a = 2 * math.pi * k / 8
            sphere(b, METAL, (x + 1.25 * math.cos(a), y - 1.5, z + 1.25 * math.sin(a)), 0.28, segs=8, rings=6)
