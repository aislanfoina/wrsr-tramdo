"""Scan the running SOVIET64's committed read-write memory for a byte string.
    python tools/dev/memscan.py sr_rocketry"""
import ctypes, ctypes.wintypes as w, sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import memprobe as m

class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p), ('AllocationProtect', w.DWORD),
                ('PartitionId', w.WORD), ('RegionSize', ctypes.c_size_t), ('State', w.DWORD), ('Protect', w.DWORD), ('Type', w.DWORD)]

def regions(h):
    addr = 0
    mbi = MBI()
    while m.k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base = mbi.BaseAddress or 0
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and mbi.RegionSize < (512 << 20):
            yield base, mbi.RegionSize
        addr = base + mbi.RegionSize
        if addr >= 0x7FFFFFFFFFFF:
            break

def scan(p, needle):
    hits = []
    for base, size in regions(p.h):
        data = p.read(base, size)
        if not data:
            continue
        i = data.find(needle)
        while i >= 0:
            hits.append(base + i)
            i = data.find(needle, i + 1)
    return hits

if __name__ == '__main__':
    m.k32.VirtualQueryEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    p = m.Proc(m.pid_of())
    for a in scan(p, sys.argv[1].encode() + b'\0'):
        print(hex(a))
