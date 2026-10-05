"""Read-only probe of the running SOVIET64: find a building by object name and list, per
person-record offset, how many citizens hold a pointer to it (to find workplace/home fields).

    python tools/dev/memprobe.py sr_training [span]

The game context is the static object at RVA 0x9D4F10 (passed to TickAllBuildings from
0x105E68); buildings vector at +0x11B08, persons at +0x126A8, building typedesc at +0x318
whose first bytes are the ident "<item>/<object>".
"""
import collections
import ctypes
import ctypes.wintypes as w
import struct
import subprocess
import sys

CTX_RVA = 0x9D4F10
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
k32.OpenProcess.restype = w.HANDLE
k32.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def pid_of(name='SOVIET64.exe'):
    out = subprocess.run(['tasklist', '/fi', 'imagename eq ' + name, '/fo', 'csv', '/nh'], capture_output=True, text=True).stdout
    for l in out.splitlines():
        if name in l:
            return int(l.split('","')[1])
    sys.exit('game not running')


class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(0x0410, False, pid)          # QUERY_INFORMATION | VM_READ
        if not self.h:
            sys.exit('OpenProcess failed %d' % ctypes.get_last_error())
        mods = (w.HMODULE * 1)()
        need = w.DWORD()
        psapi.EnumProcessModulesEx(self.h, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
        self.base = mods[0]

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def q(self, addr):
        b = self.read(addr, 8)
        return struct.unpack('<Q', b)[0] if b else 0

    def vec(self, addr):
        b, e = self.q(addr), self.q(addr + 8)
        if not b or e < b or (e - b) // 8 > 500000:
            return []
        raw = self.read(b, e - b) or b''
        return list(struct.unpack('<%dQ' % (len(raw) // 8), raw))

    def ident(self, bld):
        td = self.q(bld + 0x318)
        s = self.read(td, 64) if td else None
        return s.split(b'\0')[0].decode('ascii', 'replace') if s else ''


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else 'sr_training'
    span = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x800
    p = Proc(pid_of())
    ctx = p.base + CTX_RVA
    blds = p.vec(ctx + 0x11B08)
    targets = [b for b in blds if p.ident(b).split('/')[-1] == want]
    print('exe base %#x, %d buildings, targets %s' % (p.base, len(blds), [hex(t) for t in targets]))
    if not targets:
        return
    tset = set(targets)
    persons = p.vec(ctx + 0x126A8)
    hits = collections.Counter()
    edu = collections.defaultdict(list)
    for per in persons:
        raw = p.read(per, span)
        if not raw:
            continue
        for off in range(0, span - 7, 8):
            if struct.unpack_from('<Q', raw, off)[0] in tset:
                hits[off] += 1
                e, age = struct.unpack_from('<f', raw, 0xA8)[0], struct.unpack_from('<f', raw, 0xD4)[0]
                edu[off].append((round(e, 2), round(age, 1)))
    print('%d persons scanned' % len(persons))
    for off, n in sorted(hits.items()):
        print('  person+%#05x -> %s : %d citizens  (education, age) sample %s' % (off, want, n, edu[off][:8]))


if __name__ == '__main__':
    main()
