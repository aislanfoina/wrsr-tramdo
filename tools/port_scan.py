"""Find the plugins' hook targets in a new SOVIET64.exe build.

    python tools/port_scan.py [path to SOVIET64.exe]            # find each hook's prologue in a new build
    python tools/port_scan.py --verify [path to SOVIET64.exe]   # check the sources' addresses against a build

Every inline hook records the prologue it expects (the k*Pro arrays in the plugin sources); this
searches the new build's .text for each, keeps only matches that are function starts in the
build's own .pdata table, and prints them with their distance from the old address. Game updates
shift code by region (1.1.1.9 -> 1.1.1.13: clusters at 0, -0x80, -0x70, +0x1A0, +0x20, per
TesmioLoader's port notes), so the right match is the one at a plausible small distance; more than
one candidate needs checking by what the body does. Functions the plugins only call (no prologue
recorded) are mapped by hand from inside the hooked ones - see the PORT notes in each plugin.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe import PE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.environ.get('WRSR_GAME', r'C:\Program Files (x86)\Steam\steamapps\common\SovietRepublic')
SOURCES = [s for s in ('mod/plugins/spacerace/spacerace.cpp', 'mod/plugins/experts/experts.cpp',
                        'mod/plugins/tramdo/tramdo.cpp', 'mod/plugins/resources/resources.cpp')
           if os.path.exists(os.path.join(ROOT, s))]       # each mod's repo carries only its own plugins

# prologue array -> the #define naming its target, per source (an array's own name differs from the define's)
TARGET_OF = {'kEnumPro': 'RVA_SCEN_ENUM', 'kTickPro': 'RVA_TICK_ALL', 'kResFieldPro': 'RVA_RES_FIELD',
             'kCanUsePro': 'RVA_CAN_USE', 'kDoTickPro': 'RVA_DO_TICK', 'kSetLengthPro': 'RVA_SET_LENGTH',
             'kMissingPro': 'RVA_MISSING_RESEARCH', 'kResourceGetPrologue': 'DEFAULT_RESOURCEGET_RVA',
             'kPricePassPrologue': 'DEFAULT_PRICEPASS_RVA', 'kCustomsTickPrologue': 'P_CUSTOMHOUSE_TICK_RVA'}


def arrays(src):
    """name -> bytes of every `static const unsigned char/BYTE kX[] = { ... };` in a source."""
    out = {}
    for m in re.finditer(r'static const (?:unsigned char|BYTE)\s+(k\w+)\s*\[\d*\]\s*=\s*\{(.*?)\};', src, re.S):
        body = re.sub(r'//[^\n]*', '', m.group(2))
        vals = re.findall(r'0x([0-9A-Fa-f]{2})\b', body)
        out[m.group(1)] = bytes(int(v, 16) for v in vals)
    return out


def define(src, name):
    m = re.search(r'#define\s+%s\s+0x([0-9A-Fa-f]+)' % name, src)
    return int(m.group(1), 16) if m else None


def verify(pe):
    """Every hook define in the sources against the build: the bytes at the address must be its prologue."""
    bad = 0
    for rel in SOURCES:
        src = open(os.path.join(ROOT, rel), encoding='utf-8', errors='replace').read()
        for name, pat in arrays(src).items():
            if name not in TARGET_OF:
                continue
            rva = define(src, TARGET_OF[name])
            ok = rva is not None and pe.read(rva, len(pat)) == pat
            bad += not ok
            print('%-5s %-11s %-24s 0x%X' % ('ok' if ok else 'FAIL', os.path.basename(rel)[:-4], TARGET_OF[name], rva or 0))
    print('%d mismatch(es)' % bad)
    return bad


def main():
    args = [a for a in sys.argv[1:] if a != '--verify']
    exe = args[0] if args else os.path.join(GAME, 'SOVIET64.exe')
    pe = PE(exe)
    if '--verify' in sys.argv:
        sys.exit(1 if verify(pe) else 0)
    starts = {b for b, _e in pe.pdata}
    print('%s: %d .pdata functions' % (exe, len(starts)))
    for rel in SOURCES:
        src = open(os.path.join(ROOT, rel), encoding='utf-8', errors='replace').read()
        for name, pat in arrays(src).items():
            if name not in TARGET_OF or len(pat) < 8:
                continue
            old = define(src, TARGET_OF[name])
            hits = pe.find(pat, limit=200)
            fn = [h for h in hits if h in starts]
            fn.sort(key=lambda h: abs(h - old) if old else h)
            show = ', '.join('0x%X (%+#x)' % (h, h - old) if old else '0x%X' % h for h in fn[:4])
            print('%-11s %-24s old 0x%-7X %2d hits, %2d function starts: %s' % (
                os.path.basename(rel)[:-4], TARGET_OF[name], old or 0, len(hits), len(fn), show or '-'))


if __name__ == '__main__':
    main()
