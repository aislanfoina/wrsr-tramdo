"""Procedural textures for the Space Race kit: clean Soviet concrete, painted
steel, glazing, lattice-free structural paints, a titanium finish.

Same approach as tradepost_textures.py (whose helpers it reuses): every texture
tiles, gets a DXT1 .dds with a mip chain for the game and a .png twin for the
Blender preview renders. Box mapping in mmkit puts image-up = world-up on
walls, so facades are drawn upright.

    python tools/space_textures.py <outdir>

TILE below is the world size in metres one texture repeat covers; srkit.py
imports it so geometry and textures agree.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradepost_textures as tt  # noqa: E402
from tradepost_textures import _tile_noise, _norm, _mix, _col, _to_img, _grime  # noqa: E402

rng = np.random.default_rng(1957)

from space_palette import TILE, MATS, EMISSIVE  # noqa: E402,F401


def flat(n, rgb, var=0.08, cells=10):
    return np.broadcast_to(_col(rgb), (n, n, 3)) * (1 - var + 2 * var * _tile_noise(n, cells, 4)[..., None])


def concrete(n=1024):
    """Cast slabs 3 x 3 m (four per 12 m tile), each a slightly different shade, dark joints."""
    img = flat(n, (132, 131, 125), 0.06, 12)
    s = n // 4
    for i in range(4):
        for j in range(4):
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] *= rng.uniform(0.93, 1.05)
    speck = _tile_noise(n, 96, 2)
    img = _mix(img, np.broadcast_to(_col((120, 118, 110)), (n, n, 3)), (speck > 0.7)[..., None] * 0.25)
    y = np.arange(n)
    joint = ((y % s) < 3).astype(np.float32)
    img = _mix(img, np.broadcast_to(_col((95, 93, 88)), (n, n, 3)), joint[:, None, None] * 0.8)
    img = _mix(img, np.broadcast_to(_col((95, 93, 88)), (n, n, 3)), joint[None, :, None] * 0.8)
    return _grime(n, img, 0.18, 5)


def scorch(n=1024):
    base = flat(n, (95, 92, 86), 0.1, 8)
    soot = _norm(_tile_noise(n, 5, 5))
    img = _mix(base, np.broadcast_to(_col((28, 26, 25)), (n, n, 3)), np.clip(soot * 1.4 - 0.2, 0, 1)[..., None])
    streak = _norm(np.cumsum(_tile_noise(n, 40, 2) - 0.5, axis=0) % 5.0)
    img = _mix(img, np.broadcast_to(_col((50, 44, 38)), (n, n, 3)), (streak > 0.75)[..., None] * 0.4)
    return img


def painted(rgb, n=512, seams=4, rivets=True, var=0.05):
    img = flat(n, rgb, var, 8)
    im = _to_img(img)
    d = ImageDraw.Draw(im)
    dark = tuple(int(c * 0.72) for c in rgb)
    step = n // seams
    for k in range(0, n, step):
        d.line([(0, k), (n, k)], fill=dark, width=2)
        if rivets:
            for j in range(step // 4, n, step // 2):
                d.ellipse([j - 2, k + 5, j + 2, k + 9], fill=dark)
    arr = np.asarray(im).astype(np.float32) / 255
    return _grime(n, arr, 0.12, 6)


def white(n=512):
    return painted((200, 202, 198), n, seams=2)


def grey(n=512):
    return painted((126, 138, 140), n)


def green(n=512):
    return painted((96, 112, 78), n)


def red(n=512):
    return painted((168, 34, 30), n, seams=2, rivets=False)


def blue(n=512):
    return painted((70, 110, 150), n, seams=2, rivets=False)


def stripes(n=512):
    """Aviation warning bands: 4 m red, 4 m white per 8 m tile."""
    img = np.zeros((n, n, 3), np.float32)
    img[: n // 2] = _col((200, 45, 35))
    img[n // 2:] = _col((236, 234, 228))
    img *= (0.94 + 0.08 * _tile_noise(n, 8, 3))[..., None]
    return _grime(n, img, 0.1, 5)


def glass(n=1024, lit=False):
    """4 floors x 4 bays (3.6 m each): a ribbon window over a plaster spandrel.
    lit=True draws the emissive twin: a random half of the windows glowing."""
    cell = n // 4
    if lit:
        img = np.zeros((n, n, 3), np.float32)
    else:
        img = flat(n, (206, 200, 186), 0.05, 12)
    im = _to_img(img)
    d = ImageDraw.Draw(im)
    for fy in range(4):
        for bx in range(4):
            x0 = bx * cell; y0 = fy * cell
            wx0, wx1 = x0 + int(cell * 0.06), x0 + int(cell * 0.94)
            wy0, wy1 = y0 + int(cell * 0.22), y0 + int(cell * 0.72)
            if lit:
                if rng.random() < 0.5:
                    c = tuple(int(v) for v in (rng.uniform(200, 255), rng.uniform(170, 220), rng.uniform(90, 150)))
                    d.rectangle([wx0, wy0, wx1, wy1], fill=c)
                continue
            shade = int(rng.uniform(40, 75))
            d.rectangle([wx0, wy0, wx1, wy1], fill=(shade, shade + 18, shade + 34))
            d.line([(wx0, wy0 + int((wy1 - wy0) * 0.3)), (wx1, wy0 + int((wy1 - wy0) * 0.3))], fill=(225, 225, 220), width=4)
            for m in range(1, 3):
                mx = wx0 + (wx1 - wx0) * m // 3
                d.line([(mx, wy0), (mx, wy1)], fill=(225, 225, 220), width=5)
            d.rectangle([wx0, wy0, wx1, wy1], outline=(215, 215, 210), width=5)
            d.rectangle([wx0 - 4, wy1, wx1 + 4, wy1 + 7], fill=(150, 146, 136))
    arr = np.asarray(im).astype(np.float32) / 255
    return arr if lit else _grime(n, arr, 0.12, 5)


def stucco(n=1024, lit=False):
    """Stalinist facade: cream render, 4 x 4 punched windows with white surrounds."""
    cell = n // 4
    img = np.zeros((n, n, 3), np.float32) if lit else flat(n, (214, 196, 160), 0.05, 12)
    im = _to_img(img)
    d = ImageDraw.Draw(im)
    for fy in range(4):
        for bx in range(4):
            x0 = bx * cell; y0 = fy * cell
            wx0, wx1 = x0 + int(cell * 0.32), x0 + int(cell * 0.68)
            wy0, wy1 = y0 + int(cell * 0.18), y0 + int(cell * 0.78)
            if lit:
                if rng.random() < 0.45:
                    d.rectangle([wx0, wy0, wx1, wy1], fill=(240, 200, 120))
                continue
            d.rectangle([wx0 - 10, wy0 - 10, wx1 + 10, wy1 + 14], fill=(236, 230, 214))
            d.rectangle([wx0, wy0, wx1, wy1], fill=(48, 58, 70))
            d.line([((wx0 + wx1) // 2, wy0), ((wx0 + wx1) // 2, wy1)], fill=(230, 226, 214), width=5)
            d.line([(wx0, wy0 + (wy1 - wy0) // 3), (wx1, wy0 + (wy1 - wy0) // 3)], fill=(230, 226, 214), width=5)
        if not lit:
            d.rectangle([0, fy * cell + cell - 8, n, fy * cell + cell - 2], fill=(190, 174, 142))
    arr = np.asarray(im).astype(np.float32) / 255
    return arr if lit else _grime(n, arr, 0.15, 5)


def brick(n=512):
    """Sand-lime (silicate) brick, the pale yellow of 1950s Soviet industry."""
    img = flat(n, (212, 196, 150), 0.07, 16)
    im = _to_img(img)
    d = ImageDraw.Draw(im)
    rows = 32
    h = n // rows
    for r in range(rows):
        y = r * h
        d.line([(0, y), (n, y)], fill=(150, 142, 120), width=2)
        off = (h * 2) if r % 2 else 0
        for x in range(-off, n, h * 4):
            d.line([(x, y), (x, y + h)], fill=(150, 142, 120), width=2)
    arr = np.asarray(im).astype(np.float32) / 255
    return _grime(n, arr, 0.2, 6)


def roof(n=512):
    img = flat(n, (70, 70, 72), 0.12, 10)
    y = np.arange(n)
    seam = ((y % (n // 8)) < 3).astype(np.float32)
    img = _mix(img, np.broadcast_to(_col((45, 45, 46)), (n, n, 3)), seam[:, None, None] * 0.7)
    return _grime(n, img, 0.25, 4)


def asphalt(n=512):
    img = flat(n, (64, 64, 62), 0.1, 30)
    speck = _tile_noise(n, 120, 2)
    img = _mix(img, np.broadcast_to(_col((120, 118, 112)), (n, n, 3)), (speck > 0.72)[..., None] * 0.4)
    return _grime(n, img, 0.2, 4)


def ground(n=1024):
    """Steppe lawn in the game's own grass tones (olive, sampled at about (108, 97, 48) in daylight),
    mottled with darker tufts and a few dry patches, so a lot reads as grass rather than sand."""
    base = _tile_noise(n, 8, 5)
    img = _mix(np.broadcast_to(_col((78, 82, 40)), (n, n, 3)), np.broadcast_to(_col((100, 100, 50)), (n, n, 3)), base)
    tufts = _tile_noise(n, 96, 3)
    img = _mix(img, np.broadcast_to(_col((60, 70, 34)), (n, n, 3)), np.clip((tufts - 0.55) * 3, 0, 1)[..., None] * 0.6)
    dry = _tile_noise(n, 12, 4)
    img = _mix(img, np.broadcast_to(_col((118, 106, 62)), (n, n, 3)), np.clip((dry - 0.7) * 3, 0, 1)[..., None] * 0.5)
    return _grime(n, img, 0.1, 6)


def metal(n=512):
    streak = _tile_noise(n, 4, 3)
    img = np.broadcast_to(_col((170, 176, 180)), (n, n, 3)) * (0.85 + 0.2 * np.repeat(_tile_noise(n, 64, 2)[:1], n, 0)[..., None] * streak[..., None])
    return _grime(n, img, 0.15, 6)


def dark(n=256):
    return flat(n, (40, 42, 45), 0.1, 8)


def glow(n=64):
    return np.broadcast_to(_col((255, 236, 190)), (n, n, 3)).astype(np.float32)


def black(n=32):
    return np.zeros((n, n, 3), np.float32)


def corr(n=512):
    x = np.arange(n)[None, :]
    ridge = 0.5 + 0.5 * np.sin(x / n * 2 * np.pi * 16)
    img = np.broadcast_to(_col((178, 182, 180)), (n, n, 3)) * (0.7 + 0.3 * np.broadcast_to(ridge, (n, n)))[..., None]
    return _grime(n, img, 0.15, 5)


def hazard(n=256):
    y, x = np.mgrid[0:n, 0:n]
    band = ((x + y) // (n // 4)) % 2
    img = np.where(band[..., None] == 0, _col((226, 180, 30)), _col((30, 30, 30))).astype(np.float32)
    return _grime(n, img, 0.15, 4)


def titanium(n=512):
    """The monument cladding: bright polished panels with vertical brushing."""
    brush = np.repeat(_tile_noise(n, 96, 2)[:1], n, 0)
    img = np.broadcast_to(_col((176, 180, 184)), (n, n, 3)) * (0.86 + 0.18 * brush)[..., None]
    y = np.arange(n)
    seam = ((y % (n // 4)) < 2).astype(np.float32)
    img = _mix(img, np.broadcast_to(_col((140, 144, 148)), (n, n, 3)), seam[:, None, None] * 0.6)
    return img


def frost(n=512):
    img = flat(n, (212, 216, 222), 0.06, 20)
    rime = _tile_noise(n, 48, 3)
    img = _mix(img, np.broadcast_to(_col((200, 214, 226)), (n, n, 3)), np.clip((rime - 0.55) * 3, 0, 1)[..., None] * 0.5)
    return img


MATERIALS = {
    'sr_concrete': concrete, 'sr_scorch': scorch, 'sr_white': white, 'sr_grey': grey, 'sr_green': green,
    'sr_red': red, 'sr_stripes': stripes, 'sr_glass': glass, 'sr_stucco': stucco, 'sr_brick': brick,
    'sr_roof': roof, 'sr_asphalt': asphalt, 'sr_ground': ground, 'sr_metal': metal, 'sr_dark': dark,
    'sr_glow': glow, 'sr_corr': corr, 'sr_hazard': hazard, 'sr_titanium': titanium, 'sr_frost': frost,
    'sr_blue': blue,
    'sr_black': black, 'sr_glass_e': lambda: glass(lit=True), 'sr_stucco_e': lambda: stucco(lit=True),
}


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    sheet = []
    for name, fn in MATERIALS.items():
        im = _to_img(fn())
        im.save(os.path.join(outdir, name + '.png'))
        tt.save_dds_mips(im, os.path.join(outdir, name + '.dds'), 'DXT1')
        sheet.append((name, im))
        print('%-14s %4dx%-4d' % (name, im.size[0], im.size[1]))
    # contact sheet for a quick look
    cols = 6
    rows = (len(sheet) + cols - 1) // cols
    cs = Image.new('RGB', (cols * 160, rows * 176), (30, 30, 30))
    d = ImageDraw.Draw(cs)
    for i, (name, im) in enumerate(sheet):
        x, y = (i % cols) * 160, (i // cols) * 176
        cs.paste(im.resize((150, 150)), (x + 5, y + 5))
        d.text((x + 6, y + 158), name, fill=(230, 230, 230))
    cs.save(os.path.join(outdir, '_sheet.png'))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'build/space_textures')
