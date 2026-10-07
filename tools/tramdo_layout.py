"""The tram distribution offices' track layouts, taken from the game's own tram buildings, whose
internal tram tracks, trolley wires, parking lanes and service track are proven in game:

  tramdo_small  the tram end station (tram_endstation.ini): 6 parking lanes of 38 m, in a loop
  tramdo_large  the big tram depot (tram_depo_big.ini): 8 parking lanes, stretched 1.25x lengthwise
                (50 m lanes for the long sets; straight track stays straight, curves only get gentler)

An office holds one tram set per parking lane ($VEHICLE_PARKING): the game's road offices have
exactly as many places as parking spots, and a full set of lanes reads "depot or workplace is full".

    python tools/tramdo_layout.py [out.png]      # plots both layouts (default build/tramdo/layout.png)

Import-free of Blender: tools/tramdo_scene.py builds the models around these lines, and writes them
into building.ini.
"""
import os
import re

GAME = os.environ.get('WRSR_GAME', r'C:\Program Files (x86)\Steam\steamapps\common\SovietRepublic')
TYPES = os.path.join(GAME, 'media_soviet', 'buildings_types')
DEPOT = os.path.join(TYPES, 'tram_depo_small.ini')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the two offices: object name -> source layout, lengthwise (x) stretch, display name and the longest
# tram set it takes in metres (0 = no limit; the plugin's limit_<object> enforces it)
SIZES = {'tramdo_small': {'src': 'tram_endstation.ini', 'scale': 1.0, 'limit': 30.0,
                          'name': 'Tram Distribution Office (small trams)'},
         'tramdo_large': {'src': 'tram_depo_big.ini', 'scale': 1.25, 'limit': 0.0,
                          'name': 'Tram Distribution Office (large trams)'}}

# lines that carry the depot's own identity or logic, not geometry: the office writes its own
SKIP = ('$NAME', '$TYPE_', '$SUBTYPE_', '$MENU_SFX', '$COST_', '$ROADVEHICLE_', 'end')
# keyword lines whose numbers are coordinates: which number positions are x
INLINE_X = {'$VEHICLE_PARKING': (0, 3), '$VEHICLE_STATION': (0, 3)}
PID_LINES = ('_POINT_PID',)                  # "<pid> x y z": x is the second number
# keywords followed by coordinate lines ("x y z", or "x z" for the dead square)
BLOCKS = ('$CONNECTION', '$CONNECTIONS_ROAD_DEAD_SQUARE')

NUM = re.compile(r'^-?\d+(\.\d+)?$')


def _fmt(v):
    return ('%.4f' % v).rstrip('0').rstrip('.') if v != int(v) else '%.1f' % v


def geometry(scale=1.0, src=DEPOT):
    """The depot's geometry lines, x stretched by scale. Returns (lines, parsed) where parsed holds the
    pieces by keyword for modelling: {'$CONNECTION_TRAMROAD_DEAD': [((x,y,z),(x,y,z)), ...], ...}."""
    lines, parsed = [], {}
    current, pts = None, []

    def flush():
        if current and pts:
            parsed.setdefault(current, []).append(tuple(pts))

    for raw in open(src, encoding='utf-8', errors='replace').read().replace('\r\n', '\n').split('\n'):
        line = raw.strip()
        if not line:
            continue
        tok = line.split()
        if tok[0].startswith('$') or tok[0] == 'end':
            flush()
            current, pts = None, []
            if tok[0].startswith(SKIP) or tok[0] == 'end':
                continue
            nums = tok[1:]
            if tok[0] in INLINE_X:
                vals = [float(n) for n in nums]
                for i in INLINE_X[tok[0]]:
                    vals[i] *= scale
                lines.append('%s %s' % (tok[0], ' '.join(_fmt(v) for v in vals)))
                parsed.setdefault(tok[0], []).append(((vals[0], vals[1], vals[2]), (vals[3], vals[4], vals[5])))
                continue
            if tok[0].endswith(PID_LINES):
                vals = [float(n) for n in nums]
                vals[1] *= scale
                lines.append('%s %d %s' % (tok[0], int(vals[0]), ' '.join(_fmt(v) for v in vals[1:])))
                continue
            lines.append(line)
            if tok[0].startswith(BLOCKS):
                current = tok[0]
            continue
        if current and all(NUM.match(t) for t in tok):
            vals = [float(t) for t in tok]
            vals[0] *= scale
            lines.append(' '.join(_fmt(v) for v in vals))
            pts.append(tuple(vals))
            continue
        lines.append(line)
    flush()
    return lines, parsed


def layout(key):
    """geometry() of an office's source layout, stretched."""
    size = SIZES[key]
    return geometry(size['scale'], os.path.join(TYPES, size['src']))


def cost_stops(key):
    """The source building's construction stops ($COST_WORK_VEHICLE_STATION x y z x y z), stretched."""
    size = SIZES[key]
    stops = []
    for raw in open(os.path.join(TYPES, size['src']), encoding='utf-8', errors='replace'):
        t = raw.split()
        if len(t) == 7 and t[0] == '$COST_WORK_VEHICLE_STATION':
            v = [float(n) for n in t[1:]]
            stops.append((v[0] * size['scale'], v[2], v[3] * size['scale'], v[5]))
    return stops


def bounds(parsed):
    """The footprint from the dead square: (x0, z0, x1, z1)."""
    sq = parsed['$CONNECTIONS_ROAD_DEAD_SQUARE'][0]
    (xa, za), (xb, zb) = sq[0], sq[1]
    return min(xa, xb), min(za, zb), max(xa, xb), max(za, zb)


def plot(out):
    from PIL import Image, ImageDraw
    colours = {'$CONNECTION_TRAMROAD_DEAD': (200, 40, 40), '$CONNECTION_TRAMTROLLEYS_DEAD': (40, 90, 200),
               '$VEHICLE_PARKING': (30, 150, 60), '$VEHICLE_STATION': (230, 150, 0), '$CONNECTION_ROAD': (90, 90, 90),
               '$CONNECTION_ROAD_DEAD': (150, 150, 150)}
    panels = []
    for key, size in SIZES.items():
        scale = size['scale']
        _lines, parsed = layout(key)
        x0, z0, x1, z1 = bounds(parsed)
        k = 8
        W, H = int((x1 - x0 + 20) * k), int((z1 - z0 + 20) * k)
        im = Image.new('RGB', (W, H + 24), (250, 248, 240))
        d = ImageDraw.Draw(im)
        P = lambda x, z: ((x - x0 + 10) * k, (z1 + 10 - z) * k + 24)
        d.rectangle([P(x0, z1), P(x1, z0)], outline=(0, 0, 0))
        for kw, segs in parsed.items():
            c = colours.get(kw)
            if not c:
                continue
            for s in segs:
                if len(s) >= 2:
                    d.line([P(s[0][0], s[0][2]), P(s[1][0], s[1][2])], fill=c, width=3 if 'PARKING' in kw else 2)
                elif len(s) == 1:
                    d.ellipse([P(s[0][0], s[0][2])[0] - 4, P(s[0][0], s[0][2])[1] - 4, P(s[0][0], s[0][2])[0] + 4, P(s[0][0], s[0][2])[1] + 4], outline=c)
        d.text((6, 4), '%s  x %.1f..%.1f  z %.1f..%.1f  (stretch %.2f)' % (key, x0, x1, z0, z1, scale), fill=(0, 0, 0))
        panels.append(im)
    out_im = Image.new('RGB', (max(p.width for p in panels), sum(p.height for p in panels)), (255, 255, 255))
    y = 0
    for p in panels:
        out_im.paste(p, (0, y))
        y += p.height
    os.makedirs(os.path.dirname(out), exist_ok=True)
    out_im.save(out)
    print('layout ->', out)


if __name__ == '__main__':
    import sys
    plot(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'tramdo', 'layout.png'))
