"""Read-only probe of the running game (1.2.0.9 offsets): the Tram DO offices and every tram.

    python tools/dev/tramprobe.py [state.json]

Lists tramdo* buildings and every vehicle whose type is a rail locomotive in the tram train group
(or comes from a known tram pack), with its position; with a state file, also how far each moved
since the previous run (the file is rewritten each time).
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memprobe import Proc, pid_of  # noqa: E402

CTX = 0xA1EF20
CTX_BUILDINGS, CTX_VEHICLES = 0x11BB8, 0x128C8
BLD_TYPEDESC, VEH_TYPE, VEH_POS = 0x318, 0x1748, 0xE18   # world matrix +0xD98, its position copy +0x80
VT_IDENT, VT_KIND, VT_GROUPS = 0x200, 0x2B8, 0x9708
TRAM_PACKS = ('3563301077/', '3586205860/')


def main():
    p = Proc(pid_of())
    ctx = p.base + CTX

    def cstr(a, n=64):
        b = p.read(a, n)
        return b.split(b'\0')[0].decode('latin1', 'replace') if b else ''

    offices = []
    for b in p.vec(ctx + CTX_BUILDINGS):
        ident = p.ident(b)
        if '/tramdo' in ident:
            offices.append((hex(b), ident))
    print('offices:', offices)

    trams = {}
    for v in p.vec(ctx + CTX_VEHICLES):
        vt = p.q(v + VEH_TYPE)
        if not vt:
            continue
        ident = cstr(vt + VT_IDENT)
        kind = struct.unpack('<i', p.read(vt + VT_KIND, 4) or b'\0\0\0\0')[0]
        if not ident.startswith(TRAM_PACKS) and kind != 4:
            continue
        gb, ge = p.q(vt + VT_GROUPS), p.q(vt + VT_GROUPS + 8)
        groups = list(struct.unpack('<%di' % ((ge - gb) // 4), p.read(gb, ge - gb))) if gb and 0 < ge - gb < 256 else []
        pos = struct.unpack('<3f', p.read(v + VEH_POS, 12) or b'\0' * 12)
        if ident.startswith(TRAM_PACKS):
            trams[hex(v)] = {'type': ident, 'kind': kind, 'groups': groups, 'pos': pos}
    print('tram-pack vehicles: %d' % len(trams))

    old = {}
    state = sys.argv[1] if len(sys.argv) > 1 else None
    if state and os.path.exists(state):
        old = json.load(open(state))
    moved = 0
    for k, t in sorted(trams.items(), key=lambda kv: kv[1]['type']):
        d = ''
        if k in old:
            dist = math.dist(old[k]['pos'], t['pos'])
            moved += dist > 1.0
            d = '  moved %.0f m' % dist
        print('  %s %-40s kind %d groups %s pos (%.0f, %.0f, %.0f)%s' % (k, t['type'], t['kind'], t['groups'], *t['pos'], d))
    if old:
        print('moved since last run: %d of %d' % (moved, len(trams)))
    if state:
        json.dump(trams, open(state, 'w'))


if __name__ == '__main__':
    main()
