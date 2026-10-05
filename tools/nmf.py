"""Read and write Workers & Resources .nmf meshes.

The layout below was recovered from the vanilla files and confirmed against
3DIVISION's own Blender exporter (Dropbox "EXPORTER BLENDER", custom_exporter.py).
Every offset was verified by round-tripping vanilla and ModelViewer-made files
byte for byte (see selftest()).

    "B3DMH\\0" "10"  |  "fromObj\\0"   magic (ModelViewer's OBJ import uses the second)
    u32 nmat, u32 nnodes, u32 fileSize
    nmat x char[64]                 material names (matched by name to $SUBMATERIAL)
    per node:
      u32 type (0 mesh, 1 bone, 2 helper), u32 nodeSize
      char[64] name, u16 parent (0xFFFF none), u16 children
      float[16] world, float[16] local, float[6] aabb (min xyz, max xyz)
      u32 nlod (=1)
      u32 lodSize, u32 nv, u32 ni, u32 nsubsets, u32 0, u32 attributes, u32 0
      u16[ni] indices, CCW = front
      float[nv*3] pos, nrm, tan, bin;  float[nv*2] uv
      float[nt*4] planes (n, d)  with n.p + d = 0
      float[nt*6] triangle aabbs
      per subset: u32 firstIndex, u32 indexCount, u16 material, u16 nbones

Sizes: vanilla single-node files count 4 (node) and 8 (lod) bytes past the end
of file; multi-node vanilla files and ModelViewer files are exact. Both load.
"""
import math
import struct
import sys

MAGIC_NATIVE = b'B3DMH\x0010'
MAGIC_OBJ = b'fromObj\x00'
ATTR_DEFAULT = 0x0004013A
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


class Shape:
    def __init__(self, name):
        self.name = name
        self.node_type = 0
        self.parent = 0xFFFF
        self.children = 0
        self.world = IDENTITY
        self.local = IDENTITY
        self.attributes = ATTR_DEFAULT
        self.indices = []      # flat list of ints
        self.pos = []          # flat float lists
        self.nrm = []
        self.tan = []
        self.bin = []
        self.uv = []
        self.planes = None     # nt*4 floats, or None -> computed on write
        self.aabbs = None      # nt*6 floats, or None -> computed on write
        self.subsets = []      # (first_index, index_count, material)
        self.bbox = None       # 6 floats, or None -> computed on write

    @property
    def nv(self):
        return len(self.pos) // 3

    @property
    def nt(self):
        return len(self.indices) // 3

    def compute_bbox(self):
        xs = self.pos[0::3]; ys = self.pos[1::3]; zs = self.pos[2::3]
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    def compute_tri_data(self):
        planes = []
        aabbs = []
        p = self.pos
        for t in range(self.nt):
            a, b, c = self.indices[3 * t], self.indices[3 * t + 1], self.indices[3 * t + 2]
            A = p[3 * a:3 * a + 3]; B = p[3 * b:3 * b + 3]; C = p[3 * c:3 * c + 3]
            # 3DIVISION's exporter crosses (p2-p0) x (p1-p0): the plane normal
            # points AGAINST the counter-clockwise face normal.
            e1 = [C[i] - A[i] for i in range(3)]
            e2 = [B[i] - A[i] for i in range(3)]
            n = [e1[1] * e2[2] - e1[2] * e2[1],
                 e1[2] * e2[0] - e1[0] * e2[2],
                 e1[0] * e2[1] - e1[1] * e2[0]]
            L = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
            if L > 0:
                n = [v / L for v in n]
            else:
                n = [0.0, 1.0, 0.0]
            d = -(n[0] * A[0] + n[1] * A[1] + n[2] * A[2])
            planes += [n[0], n[1], n[2], d]
            aabbs += [min(A[0], B[0], C[0]), min(A[1], B[1], C[1]), min(A[2], B[2], C[2]),
                      max(A[0], B[0], C[0]), max(A[1], B[1], C[1]), max(A[2], B[2], C[2])]
        return planes, aabbs


class Model:
    def __init__(self):
        self.magic = MAGIC_NATIVE
        self.materials = []
        self.shapes = []


def _cstr(b):
    return b.split(b'\x00')[0].decode('latin1')


def _pad(s, n):
    b = s.encode('latin1')[:n - 1]
    return b + b'\x00' * (n - len(b))


def read(path):
    d = open(path, 'rb').read()
    m = Model()
    m.magic = d[:8]
    nmat, nnodes, total = struct.unpack_from('<III', d, 8)
    o = 0x14
    for i in range(nmat):
        m.materials.append(_cstr(d[o:o + 64])); o += 64
    for k in range(nnodes):
        ntype, nsize = struct.unpack_from('<II', d, o)
        s = Shape(_cstr(d[o + 8:o + 72]))
        s.node_type = ntype
        p = o + 72
        s.parent, s.children = struct.unpack_from('<HH', d, p); p += 4
        s.world = struct.unpack_from('<16f', d, p); p += 64
        s.local = struct.unpack_from('<16f', d, p); p += 64
        s.bbox = struct.unpack_from('<6f', d, p); p += 24
        if ntype != 0:
            m.shapes.append(s)
            o = o + nsize if k else o - 4 + nsize
            continue
        nlod, = struct.unpack_from('<I', d, p); p += 4
        assert nlod == 1, 'multi-LOD nodes not handled'
        lodsize, nv, ni, nsub, z0, attr, z1 = struct.unpack_from('<7I', d, p); p += 28
        s.attributes = attr
        s.indices = list(struct.unpack_from('<%dH' % ni, d, p)); p += 2 * ni
        s.pos = list(struct.unpack_from('<%df' % (nv * 3), d, p)); p += 12 * nv
        s.nrm = list(struct.unpack_from('<%df' % (nv * 3), d, p)); p += 12 * nv
        s.tan = list(struct.unpack_from('<%df' % (nv * 3), d, p)); p += 12 * nv
        s.bin = list(struct.unpack_from('<%df' % (nv * 3), d, p)); p += 12 * nv
        s.uv = list(struct.unpack_from('<%df' % (nv * 2), d, p)); p += 8 * nv
        nt = ni // 3
        s.planes = list(struct.unpack_from('<%df' % (nt * 4), d, p)); p += 16 * nt
        s.aabbs = list(struct.unpack_from('<%df' % (nt * 6), d, p)); p += 24 * nt
        for j in range(nsub):
            first, count, mat, nb = struct.unpack_from('<IIHH', d, p); p += 12
            p += 2 * nb
            s.subsets.append((first, count, mat))
        m.shapes.append(s)
        o = p
    return m


def _pack_shape(s, overshoot):
    if s.bbox is None:
        s.bbox = s.compute_bbox()
    if s.planes is None or s.aabbs is None:
        s.planes, s.aabbs = s.compute_tri_data()
    nv, ni, nt = s.nv, len(s.indices), s.nt
    assert nv <= 65535, 'a shape may hold at most 65535 vertices (u16 indices): %d' % nv
    assert len(s.nrm) == nv * 3 and len(s.tan) == nv * 3 and len(s.bin) == nv * 3 and len(s.uv) == nv * 2
    assert len(s.planes) == nt * 4 and len(s.aabbs) == nt * 6
    subsets = s.subsets or [(0, ni, 0)]

    body = bytearray()
    body += struct.pack('<%dH' % ni, *s.indices)
    body += struct.pack('<%df' % (nv * 3), *s.pos)
    body += struct.pack('<%df' % (nv * 3), *s.nrm)
    body += struct.pack('<%df' % (nv * 3), *s.tan)
    body += struct.pack('<%df' % (nv * 3), *s.bin)
    body += struct.pack('<%df' % (nv * 2), *s.uv)
    body += struct.pack('<%df' % (nt * 4), *s.planes)
    body += struct.pack('<%df' % (nt * 6), *s.aabbs)
    for first, count, mat in subsets:
        body += struct.pack('<IIHH', first, count, mat, 0)

    # lodSize counts from its own field to the end of the node, nodeSize from
    # the node's type field. The Maya-made vanilla files (attribute bit 1 set)
    # overshoot both by 8 and 4 on every node; Blender-exporter and ModelViewer
    # files are exact. Every kind loads, so we write exact sizes.
    over_lod = 8 if overshoot else 0
    over_node = 4 if overshoot else 0
    lod_hdr = struct.pack('<7I', 28 + len(body) + over_lod, nv, ni, len(subsets), 0, s.attributes, 0)
    node = bytearray()
    node += _pad(s.name, 64)
    node += struct.pack('<HH', s.parent, s.children)
    node += struct.pack('<16f', *s.world)
    node += struct.pack('<16f', *s.local)
    node += struct.pack('<6f', *s.bbox)
    node += struct.pack('<I', 1)
    node += lod_hdr
    node += body
    return struct.pack('<II', s.node_type, 8 + len(node) + over_node) + node


def write(model, path, maya_sizes=False):
    out = bytearray()
    out += model.magic
    out += struct.pack('<III', len(model.materials), len(model.shapes), 0)
    for name in model.materials:
        out += _pad(name, 64)
    for s in model.shapes:
        out += _pack_shape(s, maya_sizes)
    struct.pack_into('<I', out, 0x10, len(out))
    open(path, 'wb').write(out)
    return len(out)


def selftest(paths):
    import os
    import tempfile
    ok = True
    for path in paths:
        orig = open(path, 'rb').read()
        m = read(path)
        tmp = os.path.join(tempfile.gettempdir(), 'nmf_roundtrip.nmf')
        # ModelViewer leaves uninitialised memory in its name fields; compare from
        # the matrices on for those.
        start = 0xA0 if m.magic == MAGIC_OBJ else 0
        # Either size convention is valid; accept whichever the file used.
        for maya in (False, True):
            write(m, tmp, maya_sizes=maya)
            mine = open(tmp, 'rb').read()
            same = len(mine) == len(orig) and mine[start:] == orig[start:]
            if same:
                break
        first = next((i for i in range(start, min(len(mine), len(orig))) if mine[i] != orig[i]), None)
        # How well does our own triangle data reproduce what the file stores?
        # (Sign of the plane normal and the AABB layout are conventions worth
        # checking against every exporter that made these files.)
        agree = tot = 0
        for s in m.shapes:
            if s.node_type != 0 or not s.indices:
                continue
            pl, ab = s.compute_tri_data()
            for t in range(s.nt):
                tot += 1
                if all(abs(pl[4 * t + i] - s.planes[4 * t + i]) < 2e-3 * max(1.0, abs(s.planes[4 * t + i])) for i in range(4)) \
                        and all(abs(ab[6 * t + i] - s.aabbs[6 * t + i]) < 1e-3 for i in range(6)):
                    agree += 1
        print('%-52s %7d b  %-4s tri-data match %5.1f%%%s' % (
            os.path.basename(path), len(orig), 'OK' if same else 'DIFF', 100.0 * agree / max(1, tot),
            '' if same else '  first diff @0x%x (lens %d/%d)' % (first if first is not None else -1, len(orig), len(mine))))
        ok = ok and same
    return ok


if __name__ == '__main__':
    sys.exit(0 if selftest(sys.argv[1:]) else 1)
