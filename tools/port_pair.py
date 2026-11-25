"""Map every address and offset the plugins use from one SOVIET64.exe build to the next.

    python tools/port_pair.py <old SOVIET64.exe> <new SOVIET64.exe> [--root <checkout>]

Run it BEFORE editing the defines (they must still hold the old build's values), or point --root
at a checkout that does (e.g. the mod's repo at its last commit). Needs BOTH executables - keep a copy before Steam updates the game (build/game_backup/<version>/).
With only the new one, use tools/port_scan.py and re-derive by hand (see AGENTS.md, "Porting").

How: the two builds' .pdata function tables are paired (by index when the counts match - true for
1.2.0.8 -> 1.2.0.9 - otherwise by aligning the sequences of function sizes), and every pair of the
same size and instruction count is walked instruction by instruction. That yields three maps:
  - functions: old start -> new start (and the call sites that confirm it);
  - globals:   old rip-relative target -> new target;
  - offsets:   old displacement/immediate -> new, counted over the whole binary.
Then each `#define NAME 0x...` in the plugin sources is looked up in the map its value belongs to,
and printed with the evidence. A structure offset shows every new value it was paired with: one
value with all the references is the answer; a mix means the number is used by several structures
and needs a look at the functions that read that structure.

Needs capstone (pip install capstone). Takes ~15 s.
"""
import collections
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone  # noqa: E402
from pe import PE  # noqa: E402
from port_scan import ROOT, SOURCES  # noqa: E402

HEX = re.compile(r'0x[0-9a-f]+')
RIP = re.compile(r'rip ([+-]) (0x[0-9a-f]+)')


def pair_functions(old, new):
    a, b = old.pdata, new.pdata
    if len(a) == len(b):
        return list(zip(a, b)), 'by index (%d functions in both)' % len(a)
    sm = difflib.SequenceMatcher(None, [e - s for s, e in a], [e - s for s, e in b], autojunk=False)
    pairs = []
    for i, j, n in sm.get_matching_blocks():
        pairs += [(a[i + k], b[j + k]) for k in range(n)]
    return pairs, 'by size alignment (%d old, %d new, %d paired)' % (len(a), len(b), len(pairs))


def build_maps(old, new, pairs):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    funcs, data, calls = {}, collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    disp = collections.defaultdict(collections.Counter)
    walked = 0
    for (ob, oe), (nb, ne) in pairs:
        funcs[ob] = nb
        if oe - ob != ne - nb:
            continue
        x_ins = list(md.disasm(old.read(ob, oe - ob), ob))
        y_ins = list(md.disasm(new.read(nb, ne - nb), nb))
        if len(x_ins) != len(y_ins):
            continue
        walked += 1
        for x, y in zip(x_ins, y_ins):
            if x.mnemonic != y.mnemonic:
                continue
            xs, ys = x.op_str, y.op_str
            mx, my = RIP.search(xs), RIP.search(ys)
            if mx and my:
                tx = x.address + x.size + int(mx.group(2), 16) * (1 if mx.group(1) == '+' else -1)
                ty = y.address + y.size + int(my.group(2), 16) * (1 if my.group(1) == '+' else -1)
                data[tx][ty] += 1
                xs, ys = RIP.sub('rip', xs), RIP.sub('rip', ys)
            if (x.mnemonic == 'call' or x.mnemonic.startswith('j')) and xs.startswith('0x') and ys.startswith('0x'):
                if x.mnemonic == 'call':
                    calls[int(xs, 16)][int(ys, 16)] += 1
                continue
            hx, hy = HEX.findall(xs), HEX.findall(ys)
            if len(hx) == len(hy):
                for p, q in zip(hx, hy):
                    disp[int(p, 16)][int(q, 16)] += 1
    return funcs, data, calls, disp, walked


def defines(root):
    """(source, name, value) for every '#define NAME 0x...' in the plugin sources."""
    out = []
    for rel in SOURCES:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        src = open(path, encoding='utf-8').read()
        for m in re.finditer(r'^\s*#define\s+(\w+)\s+\(?0x([0-9A-Fa-f]+)\b', src, re.M):
            out.append((os.path.basename(rel), m.group(1), int(m.group(2), 16)))
    return out


def fmt_counter(c, v, top=3):
    return ', '.join('0x%X%s x%d' % (k, '' if k == v else ' (%+X)' % (k - v), n) for k, n in c.most_common(top))


def main(old_path, new_path, root=ROOT):
    old, new = PE(old_path), PE(new_path)
    pairs, how = pair_functions(old, new)
    funcs, data, calls, disp, walked = build_maps(old, new, pairs)
    print('functions paired %s; %d walked instruction by instruction' % (how, walked))
    sec = {n: (va, va + max(vs, rs)) for n, va, vs, _r, rs in old.sections}
    data_lo = min(sec[n][0] for n in ('.rdata', '.data') if n in sec)
    text_lo, text_hi = sec['.text']
    changed = 0
    for src, name, v in defines(root):
        kind, new_v, ev = 'offset', None, ''
        is_address = 'RVA' in name or name.startswith('P_')     # the sources' naming: RVA_*, *_RVA, P_*
        if not is_address:
            pass
        elif text_lo <= v < text_hi and v not in funcs:
            kind, ev = 'code', 'not a .pdata function start in the old build - map by hand'
        elif text_lo <= v < text_hi:
            kind, new_v = 'function', funcs[v]
            c = calls.get(v)
            ev = ('call sites -> ' + fmt_counter(c, new_v)) if c else 'no direct calls (hooked or reached indirectly)'
        elif v >= data_lo and v < old.sections[-1][1]:
            kind = 'global'
            c = data.get(v)
            if c:
                new_v = c.most_common(1)[0][0]
                ev = '%d refs -> %s' % (sum(c.values()), fmt_counter(c, v))
            else:
                near = sorted(k for k in data if v - 0x100 <= k <= v)
                if near:
                    k = near[-1]
                    nk = data[k].most_common(1)[0][0]
                    new_v = v + (nk - k)
                    ev = 'not referenced directly; nearest referenced global below, 0x%X -> 0x%X' % (k, nk)
        if kind == 'offset':
            c = disp.get(v)
            if c:
                new_v = c.most_common(1)[0][0]
                ev = '%d refs -> %s' % (sum(c.values()), fmt_counter(c, v))
            else:
                ev = 'never seen as a displacement or immediate'
        mark = ' '
        if new_v is not None and new_v != v:
            mark, changed = '*', changed + 1
        shown = ('0x%X' % new_v) if new_v is not None else '?'
        print('%s %-14s %-28s %-8s 0x%-8X -> %-9s %s' % (mark, src, name, kind, v, shown, ev))
    print('\n%d define(s) change (*). Hooked functions: re-check prologues with tools/port_scan.py --verify.' % changed)


if __name__ == '__main__':
    args = sys.argv[1:]
    root = ROOT
    if '--root' in args:            # read the defines from another checkout (e.g. the sources still at the old build)
        i = args.index('--root')
        root = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    main(args[0], args[1], root)
