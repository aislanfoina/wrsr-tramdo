"""Small static-RE helper over tools/pe.py + capstone: disassembly with string
annotations, call-site and lea-xref search, function lookup via .pdata."""
import re, struct, bisect, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe import PE
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

# the game folder; override with the WRSR_GAME environment variable
GAME = os.environ.get('WRSR_GAME', 'C:/Program Files (x86)/Steam/steamapps/common/SovietRepublic').rstrip('/\\') + '/'
EXE = GAME + 'SOVIET64.exe'
DLL = GAME + 'C3DDLL64.dll'


class Bin:
    def __init__(self, path):
        self.pe = PE(path)
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        t = [s for s in self.pe.sections if s[0] == '.text'][0]
        self.tva, self.traw, self.trawsz = t[1], t[3], t[4]
        self.blob = self.pe.data[self.traw:self.traw + self.trawsz]
        self.starts = [b for b, _ in self.pe.pdata]
        self.exports = self._exports()

    def _exports(self):
        d = self.pe.data
        pe_off = struct.unpack_from('<I', d, 0x3c)[0]; opt = pe_off + 24
        erva, esz = struct.unpack_from('<II', d, opt + 0x70)
        if not erva: return {}
        eo = self.rva2off(erva)
        nfun, nnames = struct.unpack_from('<II', d, eo + 0x14); afun, anames, aord = struct.unpack_from('<III', d, eo + 0x1c)
        out = {}
        for i in range(nnames):
            nrva = struct.unpack_from('<I', d, self.rva2off(anames) + i * 4)[0]
            ordn = struct.unpack_from('<H', d, self.rva2off(aord) + i * 2)[0]
            frva = struct.unpack_from('<I', d, self.rva2off(afun) + ordn * 4)[0]
            out[d[self.rva2off(nrva):self.rva2off(nrva) + 300].split(b'\0')[0].decode()] = frva
        return out

    def rva2off(self, rva):
        for name, va, vsz, raw, rawsz in self.pe.sections:
            if va <= rva < va + max(vsz, rawsz): return raw + (rva - va)

    def off2rva(self, off):
        for name, va, vsz, raw, rawsz in self.pe.sections:
            if raw <= off < raw + rawsz: return va + (off - raw)

    def read(self, rva, n): return self.pe.read(rva, n)

    def func_of(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        if i < 0: return None
        b, e = self.pe.pdata[i]
        while i > 0 and self.pe.pdata[i - 1][1] == b: i -= 1; b = self.pe.pdata[i][0]
        return b

    def func_end(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        b, e = self.pe.pdata[i]
        j = i
        while j + 1 < len(self.pe.pdata) and self.pe.pdata[j + 1][0] == self.pe.pdata[j][1] and self.pe.pdata[j + 1][0] - b < 0x40000: j += 1
        return self.pe.pdata[j][1]

    def strat(self, rva, n=48):
        raw = self.read(rva, n)
        if raw and raw[0] and all(32 <= c < 127 for c in raw[:min(4, len(raw.split(b'\0')[0]) or 1)]):
            return raw.split(b'\0')[0][:44]
        if raw and raw[0] and raw[1] == 0 and 32 <= raw[0] < 127:  # utf16
            s = raw.decode('utf-16le', 'ignore').split('\0')[0]
            if len(s) > 2: return ('L' + s[:40]).encode()
        return None

    def export_at(self, rva):
        for k, v in self.exports.items():
            if v == rva: return k
        return None

    def dis(self, a, b=None, n=None, label=None, stop_ret=False):
        b = b or (a + 0x1000)
        if label: print('=== %s %x..%x ===' % (label, a, b))
        cnt = 0
        for ins in self.md.disasm(self.read(a, b - a), a):
            s = '  %x %s %s' % (ins.address, ins.mnemonic, ins.op_str)
            m = re.search(r'rip \+ (0x[0-9a-f]+)\]', ins.op_str)
            if m:
                tgt = ins.address + ins.size + int(m.group(1), 16)
                if ins.mnemonic == 'lea':
                    st = self.strat(tgt)
                    if st: s += '   ; %r' % st
                elif ins.mnemonic == 'call' or ins.mnemonic == 'jmp':
                    imp = getattr(self, 'iat', {}).get(tgt)
                    if imp: s += '   ; %s' % imp[1]
            m = re.match(r'call 0x([0-9a-f]+)$', ins.mnemonic + ' ' + ins.op_str)
            if m:
                ex = self.export_at(int(m.group(1), 16))
                if ex: s += '   ; ' + ex
            print(s)
            cnt += 1
            if stop_ret and ins.mnemonic == 'ret': break
            if n and cnt >= n: break

    def callers(self, target):
        out = []
        for m in re.finditer(rb'\xe8', self.blob):
            i = m.start(); disp = struct.unpack_from('<i', self.blob, i + 1)[0]
            if self.tva + i + 5 + disp == target: out.append(self.tva + i)
        return out

    def xrefs(self, target, lo=0, hi=0):
        out = []
        for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', self.blob):
            i = m.start(); disp = struct.unpack_from('<i', self.blob, i + 3)[0]
            t = self.tva + i + 7 + disp
            if target - lo <= t <= target + hi: out.append((self.tva + i, t - target))
        return out

    def find_str(self, s):
        out = []
        for m in re.finditer(re.escape(s) + rb'\x00', self.pe.data):
            r = self.off2rva(m.start())
            if r: out.append(r)
        return out

    def load_iat(self):
        d = self.pe.data
        pe_off = struct.unpack_from('<I', d, 0x3c)[0]; opt = pe_off + 24
        nrva = struct.unpack_from('<I', d, opt + 0x70 + 8)[0]
        self.iat = {}
        o = self.rva2off(nrva)
        while True:
            ilt, ts, fc, name, ft = struct.unpack_from('<IIIII', d, o)
            if ilt == 0 and ft == 0: break
            dll = d[self.rva2off(name):self.rva2off(name) + 64].split(b'\0')[0].decode()
            i = 0
            while True:
                e = struct.unpack_from('<Q', d, self.rva2off(ilt) + i * 8)[0]
                if e == 0: break
                fn = '#%d' % (e & 0xffff) if e >> 63 else d[self.rva2off(e & 0x7fffffff) + 2:self.rva2off(e & 0x7fffffff) + 200].split(b'\0')[0].decode()
                self.iat[ft + i * 8] = (dll, fn); i += 1
            o += 20
        return self.iat
