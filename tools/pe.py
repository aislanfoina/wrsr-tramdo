"""Minimal PE64 reader for SOVIET64.exe reconnaissance.

Gives section layout and the .pdata function table, which is the cheapest way to
turn a documented RVA from another build into a verified function start + size in
the build actually installed here.
"""
import struct, bisect


class PE:
    def __init__(self, path):
        self.data = d = open(path, 'rb').read()
        pe = struct.unpack_from('<I', d, 0x3C)[0]
        assert d[pe:pe + 4] == b'PE\0\0', 'not a PE'
        nsec, = struct.unpack_from('<H', d, pe + 6)
        optsz, = struct.unpack_from('<H', d, pe + 20)
        opt = pe + 24
        assert struct.unpack_from('<H', d, opt)[0] == 0x20b, 'not PE32+'
        self.image_base, = struct.unpack_from('<Q', d, opt + 24)
        ndir, = struct.unpack_from('<I', d, opt + 108)
        self.dirs = [struct.unpack_from('<II', d, opt + 112 + i * 8) for i in range(ndir)]
        self.sections = []
        s = opt + optsz
        for i in range(nsec):
            name = d[s:s + 8].rstrip(b'\0').decode('ascii', 'replace')
            vsz, va, rawsz, raw = struct.unpack_from('<IIII', d, s + 8)
            self.sections.append((name, va, vsz, raw, rawsz))
            s += 40
        self._pdata = None

    def off(self, rva):
        """File offset for an RVA, or None if it lands outside raw data."""
        for _n, va, vsz, raw, rawsz in self.sections:
            if va <= rva < va + max(vsz, rawsz):
                delta = rva - va
                return raw + delta if delta < rawsz else None
        return None

    def read(self, rva, n):
        o = self.off(rva)
        return self.data[o:o + n] if o is not None else b''

    def section_of(self, rva):
        for n, va, vsz, raw, rawsz in self.sections:
            if va <= rva < va + max(vsz, rawsz):
                return n
        return None

    @property
    def pdata(self):
        """Sorted [(start_rva, end_rva)] from the exception directory."""
        if self._pdata is None:
            va, size = self.dirs[3]
            o = self.off(va)
            out = []
            for i in range(size // 12):
                b, e, _u = struct.unpack_from('<III', self.data, o + i * 12)
                if b or e:
                    out.append((b, e))
            out.sort()
            self._pdata = out
        return self._pdata

    def func(self, rva):
        """The .pdata runtime function containing rva -> (start, end, size)."""
        starts = [b for b, _ in self.pdata]
        i = bisect.bisect_right(starts, rva) - 1
        if i < 0:
            return None
        b, e = self.pdata[i]
        return (b, e, e - b) if b <= rva < e else None

    def find(self, pattern, section='.text', limit=64):
        """All RVAs of a byte pattern within a section."""
        hits = []
        for n, va, vsz, raw, rawsz in self.sections:
            if n != section:
                continue
            blob = self.data[raw:raw + rawsz]
            i = blob.find(pattern)
            while i != -1 and len(hits) < limit:
                hits.append(va + i)
                i = blob.find(pattern, i + 1)
        return hits
