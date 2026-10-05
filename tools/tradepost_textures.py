"""Procedural, tileable textures for the Survival Trade Post.

Everything is generated - no downloaded art - so the whole model is
reproducible from this repo. Each material gets a DXT1 .dds with a full mip
chain (what the game ships) and a .png twin for Blender's preview render.

    python tools/tradepost_textures.py <outdir>
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

rng = np.random.default_rng(7)


# ----------------------------------------------------------------- noise ----

def _tile_noise(n, cells, octaves=4, persistence=0.5):
    """Value noise that tiles at n px: interpolate a random lattice that wraps."""
    out = np.zeros((n, n), np.float32)
    amp = 1.0
    total = 0.0
    for o in range(octaves):
        c = cells * (2 ** o)
        lat = rng.random((c, c), np.float32)
        # bilinear upsample with wrap
        ys = np.linspace(0, c, n, endpoint=False)
        xs = np.linspace(0, c, n, endpoint=False)
        y0 = np.floor(ys).astype(int); x0 = np.floor(xs).astype(int)
        fy = (ys - y0)[:, None]; fx = (xs - x0)[None, :]
        fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
        y1 = (y0 + 1) % c; x1 = (x0 + 1) % c
        a = lat[y0][:, x0]; b = lat[y0][:, x1]; cc = lat[y1][:, x0]; d = lat[y1][:, x1]
        v = (a * (1 - fx) + b * fx) * (1 - fy) + (cc * (1 - fx) + d * fx) * fy
        out += v * amp
        total += amp
        amp *= persistence
    return out / total


def _norm(a):
    a = a - a.min()
    return a / max(1e-6, a.max())


def _rgb(r, g, b):
    return np.stack([r, g, b], -1)


def _mix(a, b, t):
    t = np.asarray(t, np.float32)[..., None] if np.ndim(t) == 2 else t
    return a * (1 - t) + b * t


def _col(c):
    return np.array(c, np.float32) / 255.0


def _to_img(arr):
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), 'RGB')


def _grime(n, img, strength=0.25, cells=8):
    g = _tile_noise(n, cells, 5)
    return img * (1 - strength * (1 - g)[..., None])


# ------------------------------------------------------------- materials ----

def rust(n=1024):
    base = _tile_noise(n, 6, 5)
    fine = _tile_noise(n, 48, 3)
    orange = _col((150, 70, 25)); brown = _col((70, 38, 22)); steel = _col((88, 82, 78))
    img = _mix(np.broadcast_to(brown, (n, n, 3)), np.broadcast_to(orange, (n, n, 3)), _norm(base) ** 1.5)
    img = _mix(img, np.broadcast_to(steel, (n, n, 3)), (fine > 0.62)[..., None] * 0.7)
    # plate seams every 256 px with rivets
    im = _to_img(img)
    d = ImageDraw.Draw(im)
    for k in range(0, n, n // 4):
        d.line([(0, k), (n, k)], fill=(45, 30, 20), width=4)
        d.line([(k, 0), (k, n)], fill=(45, 30, 20), width=4)
        for j in range(n // 32, n, n // 16):
            d.ellipse([j - 5, k + 10, j + 5, k + 20], fill=(60, 50, 45), outline=(30, 22, 18))
            d.ellipse([k + 10, j - 5, k + 20, j + 5], fill=(60, 50, 45), outline=(30, 22, 18))
    arr = np.asarray(im).astype(np.float32) / 255
    # vertical rust streaks
    streak = np.cumsum(_tile_noise(n, 32, 2) - 0.5, axis=0)
    streak = _norm(np.mod(streak, 6.0))
    arr = _mix(arr, np.broadcast_to(_col((120, 55, 20)), (n, n, 3)), (streak > 0.8)[..., None] * 0.35)
    return _grime(n, arr, 0.3)


def corrugated(n=1024):
    x = np.arange(n)[None, :]
    ridge = 0.5 + 0.5 * np.sin(x / n * 2 * np.pi * 32)
    ridge = np.broadcast_to(ridge, (n, n)).astype(np.float32)
    zinc = _col((150, 158, 160)); dark = _col((70, 76, 80))
    shade = 0.55 + 0.45 * ridge
    img = np.broadcast_to(zinc, (n, n, 3)) * shade[..., None]
    rustmap = _tile_noise(n, 5, 4)
    rustc = np.broadcast_to(_col((140, 65, 25)), (n, n, 3))
    img = _mix(img, rustc, np.clip((rustmap - 0.55) * 3, 0, 1)[..., None])
    # sheet edges (horizontal overlaps every 512 px)
    edge = ((np.arange(n)[:, None] % (n // 2)) < 6).astype(np.float32)
    img = _mix(img, np.broadcast_to(dark, (n, n, 3)), edge[..., None] * 0.8)
    return _grime(n, img, 0.35, 6)


def tarp(n=512):
    weave = _tile_noise(n, 64, 2)
    olive = _col((118, 112, 78)); tan = _col((150, 135, 95))
    img = _mix(np.broadcast_to(olive, (n, n, 3)), np.broadcast_to(tan, (n, n, 3)), _tile_noise(n, 4, 3)[..., None])
    img = img * (0.85 + 0.3 * weave[..., None])
    # patch squares
    im = _to_img(img)
    d = ImageDraw.Draw(im)
    for _ in range(5):
        x, y = rng.integers(0, n, 2)
        w, h = rng.integers(60, 160, 2)
        base = int(rng.integers(85, 130))
        c = (base + int(rng.integers(-10, 10)), base + int(rng.integers(-12, 4)), base - int(rng.integers(20, 45)))
        d.rectangle([x, y, x + w, y + h], fill=c, outline=(55, 50, 40), width=3)
    arr = np.asarray(im).astype(np.float32) / 255
    return _grime(n, arr, 0.3)


def wood(n=512):
    grain = _tile_noise(n, 3, 5, 0.6)
    y = np.arange(n)[:, None]
    planks = ((y // (n // 6)) % 2).astype(np.float32)
    light = _col((150, 120, 80)); dark = _col((95, 72, 45))
    img = _mix(np.broadcast_to(dark, (n, n, 3)), np.broadcast_to(light, (n, n, 3)), (_norm(grain) * 0.7 + planks * 0.3)[..., None])
    gap = ((y % (n // 6)) < 5).astype(np.float32)
    img = _mix(img, np.broadcast_to(_col((30, 22, 15)), (n, n, 3)), gap[..., None])
    # grain lines
    lines = np.sin((np.arange(n)[None, :] + grain * 200) * 0.9)
    img = img * (0.9 + 0.1 * lines[..., None])
    return _grime(n, img, 0.35, 5)


def ground(n=1024):
    dirt = _tile_noise(n, 8, 6, 0.55)
    gravel = _tile_noise(n, 128, 2)
    a = _col((105, 90, 70)); b = _col((70, 60, 48))
    img = _mix(np.broadcast_to(b, (n, n, 3)), np.broadcast_to(a, (n, n, 3)), _norm(dirt)[..., None])
    img = img * (0.8 + 0.4 * gravel[..., None])
    stains = _tile_noise(n, 4, 3)
    img = _mix(img, np.broadcast_to(_col((30, 28, 26)), (n, n, 3)), np.clip((stains - 0.6) * 4, 0, 1)[..., None] * 0.7)
    return img


def tire(n=512):
    y = np.arange(n)[:, None]
    tread = ((y // (n // 24)) % 2).astype(np.float32)
    img = np.broadcast_to(_col((28, 28, 30)), (n, n, 3)) * (0.7 + 0.6 * tread[..., None])
    return _grime(n, img, 0.2, 16)


def stripes(n=256):
    x = np.arange(n)[None, :]; y = np.arange(n)[:, None]
    band = (((x + y) // (n // 8)) % 2).astype(np.float32)
    img = _mix(np.broadcast_to(_col((30, 30, 30)), (n, n, 3)), np.broadcast_to(_col((225, 180, 30)), (n, n, 3)), band[..., None])
    return _grime(n, img, 0.4, 4)


def redpaint(n=512):
    chip = _tile_noise(n, 10, 4)
    img = np.broadcast_to(_col((140, 40, 30)), (n, n, 3)) * (0.8 + 0.3 * _tile_noise(n, 30, 2)[..., None])
    img = _mix(img, np.broadcast_to(_col((90, 60, 40)), (n, n, 3)), (chip > 0.68)[..., None] * 0.9)
    return _grime(n, img, 0.3)


def iron(n=512):
    img = np.broadcast_to(_col((62, 60, 58)), (n, n, 3)) * (0.75 + 0.5 * _tile_noise(n, 12, 4)[..., None])
    return _grime(n, img, 0.3)


def gravel(n=512):
    g = _tile_noise(n, 96, 2)
    img = np.broadcast_to(_col((135, 130, 122)), (n, n, 3)) * (0.5 + 0.8 * g[..., None])
    return img


def brick(n=512):
    y = np.arange(n)[:, None]; x = np.arange(n)[None, :]
    bh = n // 16; bw = n // 8
    row = y // bh
    xs = (x + (row % 2) * (bw // 2)) % bw
    mortar = ((y % bh) < 4) | (xs < 4)
    var = _tile_noise(n, 16, 2)
    img = _mix(np.broadcast_to(_col((150, 70, 50)), (n, n, 3)), np.broadcast_to(_col((110, 55, 40)), (n, n, 3)), var[..., None])
    img = _mix(img, np.broadcast_to(_col((160, 150, 135)), (n, n, 3)), mortar[..., None].astype(np.float32))
    return _grime(n, img, 0.25)


def cement(n=512):
    paper = _tile_noise(n, 40, 3)
    img = np.broadcast_to(_col((190, 175, 150)), (n, n, 3)) * (0.8 + 0.3 * paper[..., None])
    y = np.arange(n)[:, None]
    seam = ((y % (n // 4)) < 6).astype(np.float32)
    img = _mix(img, np.broadcast_to(_col((90, 80, 65)), (n, n, 3)), seam[..., None] * 0.8)
    return _grime(n, img, 0.35, 6)


def bone(n=256):
    img = np.broadcast_to(_col((215, 205, 180)), (n, n, 3)) * (0.8 + 0.3 * _tile_noise(n, 12, 3)[..., None])
    crack = _tile_noise(n, 24, 2)
    img = _mix(img, np.broadcast_to(_col((90, 80, 65)), (n, n, 3)), (crack > 0.72)[..., None] * 0.6)
    return _grime(n, img, 0.25, 6)


def concrete(n=512):
    img = np.broadcast_to(_col((140, 138, 130)), (n, n, 3)) * (0.75 + 0.4 * _tile_noise(n, 10, 5)[..., None])
    stain = _tile_noise(n, 4, 3)
    img = _mix(img, np.broadcast_to(_col((70, 68, 62)), (n, n, 3)), np.clip((stain - 0.58) * 3, 0, 1)[..., None] * 0.6)
    y = np.arange(n)[:, None]
    seam = ((y % (n // 2)) < 4).astype(np.float32)
    img = _mix(img, np.broadcast_to(_col((60, 58, 55)), (n, n, 3)), seam[..., None] * 0.7)
    return _grime(n, img, 0.3, 5)


def glow(n=64):
    return np.broadcast_to(_col((255, 200, 110)), (n, n, 3)).astype(np.float32)


def black(n=32):
    return np.zeros((n, n, 3), np.float32)


MATERIALS = {
    'tp_rust': rust, 'tp_corrugated': corrugated, 'tp_tarp': tarp, 'tp_wood': wood,
    'tp_ground': ground, 'tp_tire': tire, 'tp_stripes': stripes, 'tp_redpaint': redpaint,
    'tp_iron': iron, 'tp_gravel': gravel, 'tp_brick': brick, 'tp_cement': cement,
    'tp_glow': glow, 'tp_black': black, 'tp_bone': bone, 'tp_concrete': concrete,
}


# ------------------------------------------------------------------ dds ----

def save_dds_mips(im, path, fmt='DXT1'):
    """PIL writes a single compressed level; assemble the mip chain ourselves.
    fmt DXT1 for opaque textures, DXT5 when the alpha matters (previews)."""
    levels = []
    w, h = im.size
    cur = im.convert('RGBA' if fmt == 'DXT5' else 'RGB')
    while True:
        tmp = path + '.level.dds'
        cur.save(tmp, pixel_format=fmt)
        levels.append(open(tmp, 'rb').read()[128:])
        os.remove(tmp)
        if cur.size[0] <= 4 and cur.size[1] <= 4:
            break
        cur = cur.resize((max(4, cur.size[0] // 2), max(4, cur.size[1] // 2)), Image.LANCZOS)
    DDSD = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000   # caps|height|width|pixelformat|mipmapcount|linearsize
    hdr = struct.pack('<4sIIIIIII', b'DDS ', 124, DDSD, h, w, len(levels[0]), 0, len(levels))
    hdr += b'\x00' * 44
    hdr += struct.pack('<II4sIIIII', 32, 0x4, fmt.encode('ascii'), 0, 0, 0, 0, 0)
    hdr += struct.pack('<IIIII', 0x1000 | 0x400000 | 0x8, 0, 0, 0, 0)   # texture|mipmap|complex
    assert len(hdr) == 128
    with open(path, 'wb') as f:
        f.write(hdr)
        for lv in levels:
            f.write(lv)


def save_dds_dxt1_mips(im, path):
    save_dds_mips(im, path, 'DXT1')


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    for name, fn in MATERIALS.items():
        arr = fn()
        im = _to_img(arr)
        im.save(os.path.join(outdir, name + '.png'))
        save_dds_dxt1_mips(im, os.path.join(outdir, name + '.dds'))
        print('%-16s %4dx%-4d %7d b' % (name, im.size[0], im.size[1], os.path.getsize(os.path.join(outdir, name + '.dds'))))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'build/textures')
