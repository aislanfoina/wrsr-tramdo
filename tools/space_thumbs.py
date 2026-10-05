"""The Space Race's Steam Workshop thumbnails: Soviet-poster style, one per item.

    python tools/space_thumbs.py            # render the cut-outs in Blender, then compose
    python tools/space_thumbs.py compose    # compose from build/thumbs only
    python tools/space_thumbs.py compose collection kit    # only these posters

Renders the models with tools/space_thumb_scene.py (each rocket whole, top to bottom - a square
crop of a standing rocket loses its nose or its engines), mirrors them the way the game shows models
and puts them on posters: red sunburst, cream lettering, launch smoke, a year badge. Writes
build/thumbs/posters/*.png and each item's previewimage.png (the game refuses previews of 1 MB or
more). Needs the textures and kit from tools/build_space.py, Blender (set BLENDER if it is not in its
default folder) and the Oswald font (SIL OFL; falls back to Impact).
"""
import math
import os
import random
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = os.environ.get('BLENDER', r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')
CUTS = os.path.join(ROOT, 'build', 'thumbs')
POSTERS = os.path.join(CUTS, 'posters')
FONTS = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')

SIZE = 1024
SS = 2                                   # drawn at twice the size, then scaled down: smooth edges
W = SIZE * SS

RED = (196, 30, 36)
RED_DARK = (158, 20, 27)
CREAM = (245, 235, 214)
SHADE = (222, 208, 182)
INK = (38, 20, 17)
GOLD = (236, 186, 72)
FLAME = ((255, 246, 214), (255, 210, 74), (243, 132, 38))

# item -> (cut-out, title, Cyrillic ribbon, year, tagline); years are the rockets' in-game ones
ROCKETS = {
    'sr_sputnik': ('rk_sputnik', 'SPUTNIK', 'Р-7 «СПУТНИК»', 1957, 'THE FIRST\nSATELLITE'),
    'sr_vostok': ('rk_vostok', 'VOSTOK-K', 'ВОСТОК-К', 1960, 'THE FIRST MAN\nIN SPACE'),
    'sr_soyuz': ('rk_soyuz', 'SOYUZ', 'СОЮЗ', 1966, 'THE\nWORKHORSE'),
    'sr_proton': ('rk_proton', 'PROTON', 'ПРОТОН', 1965, 'ROUND\nTHE MOON'),
    'sr_n1': ('rk_n1', 'N1-L3', 'Н1-Л3', 1969, 'TO THE\nMOON'),
}
TARGETS = {'package': 'mod/packages/space_race', 'kit': 'mod/buildings/space_kit'}
TARGETS.update((k, 'mod/vehicles/' + k) for k in ROCKETS)


# ---------------------------------------------------------------- drawing --

def font(size, weight='Bold'):
    for name in ('Oswald-%s.ttf' % weight, 'impact.ttf'):
        path = os.path.join(FONTS, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size * SS)
    return ImageFont.load_default()


def fit(text, width, size, weight='Bold'):
    """The largest font up to size whose text fits width (unscaled pixels)."""
    while size > 10:
        f = font(size, weight)
        if max(f.getbbox(line)[2] for line in text.split('\n')) <= width * SS:
            return f
        size -= 4
    return font(size, weight)


def s(*v):
    """Unscaled coordinates to drawing ones."""
    return tuple(round(x * SS) for x in v)


def sunburst(im, center, rays=26, colors=(RED, RED_DARK), turn=0.0):
    d = ImageDraw.Draw(im)
    cx, cy = s(*center)
    far = W * 3
    for i in range(rays):
        a0 = turn + 2 * math.pi * i / rays
        a1 = turn + 2 * math.pi * (i + 1) / rays
        d.polygon([(cx, cy), (cx + far * math.cos(a0), cy + far * math.sin(a0)),
                   (cx + far * math.cos(a1), cy + far * math.sin(a1))], fill=colors[i % 2])


def vignette(im, strength=0.45):
    """Darkens the corners like an old print."""
    g = Image.radial_gradient('L').resize(im.size)        # 0 in the middle, 255 at the rim
    mask = g.point(lambda v: int(min(255, max(0, (v - 110) * 1.6)) * strength))
    im.paste(Image.new('RGB', im.size, INK), (0, 0), mask)


def paper(im, seed=7):
    """A faint print grain, the same on every run (so an unchanged poster stays byte for byte the same)."""
    rnd = random.Random(seed)
    w, h = im.width // 4, im.height // 4
    noise = Image.frombytes('L', (w, h), bytes(min(255, max(0, int(rnd.gauss(128, 28)))) for _ in range(w * h)))
    noise = noise.resize(im.size, Image.BILINEAR)
    grain = Image.merge('RGB', (noise, noise, noise))
    return Image.blend(im, grain, 0.05)


def star(d, center, r, fill, outline=None, width=0, turn=-90.0):
    cx, cy = s(*center)
    r = r * SS
    pts = []
    for i in range(10):
        a = math.radians(turn + 36 * i)
        rr = r if i % 2 == 0 else r * 0.382
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline, width=width * SS)


def text(d, xy, body, f, fill=CREAM, shadow=INK, offset=7, spacing=0, anchor='la'):
    x, y = s(*xy)
    if shadow:
        d.multiline_text((x + offset * SS, y + offset * SS), body, font=f, fill=shadow, spacing=spacing * SS, anchor=anchor)
    d.multiline_text((x, y), body, font=f, fill=fill, spacing=spacing * SS, anchor=anchor)


def ribbon(d, xy, body, f, bg=INK, fg=CREAM, pad=(22, 10)):
    """A label on a band; returns its unscaled bottom."""
    x, y = s(*xy)
    l, t, r, b = d.textbbox((x, y), body, font=f)
    px, py = pad[0] * SS, pad[1] * SS
    d.rectangle((x - px, y - py + (t - y), r + px, b + py), fill=bg)
    d.text((x, y), body, font=f, fill=fg)
    return (b + py) / SS


def badge(im, center, r, year):
    d = ImageDraw.Draw(im)
    cx, cy = s(*center)
    R = r * SS
    d.ellipse((cx - R + 8 * SS, cy - R + 8 * SS, cx + R + 8 * SS, cy + R + 8 * SS), fill=INK)
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=GOLD, outline=INK, width=6 * SS)
    d.ellipse((cx - R * 0.82, cy - R * 0.82, cx + R * 0.82, cy + R * 0.82), outline=INK, width=2 * SS)
    star(d, (center[0], center[1] - r * 0.45), r * 0.2, RED)
    d.text((cx, cy + R * 0.18), str(year), font=font(round(r * 0.62)), fill=INK, anchor='mm')


def stamp(im, center, r, ring, middle, angle=-14.0, color=CREAM, alpha=215):
    """A round rubber stamp: text around the ring, a star and a word in the middle."""
    R = r * SS
    layer = Image.new('RGBA', (2 * R + 40 * SS, 2 * R + 40 * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = layer.width / 2
    ink = color + (alpha,)
    d.ellipse((c - R, c - R, c + R, c + R), outline=ink, width=7 * SS)
    d.ellipse((c - R * 0.70, c - R * 0.70, c + R * 0.70, c + R * 0.70), outline=ink, width=3 * SS)
    f = font(round(r * 0.2))
    step = 360.0 / len(ring)
    for i, ch in enumerate(ring):
        a = math.radians(-90 + i * step)
        g = Image.new('RGBA', (f.size * 2, f.size * 2), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((f.size, f.size), ch, font=f, fill=ink, anchor='mm')
        g = g.rotate(-math.degrees(a) - 90, resample=Image.BICUBIC)
        rr = R * 0.85
        layer.alpha_composite(g, (round(c + rr * math.cos(a) - f.size), round(c + rr * math.sin(a) - f.size)))
    star(d, (c / SS, (c - R * 0.28) / SS), r * 0.17, ink)
    d.text((c, c + R * 0.2), middle, font=font(round(r * 0.3)), fill=ink, anchor='mm')
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    cx, cy = s(*center)
    im.paste(layer, (round(cx - layer.width / 2), round(cy - layer.height / 2)), layer)


def clouds(im, top, puffs, seed, focus=None, lift=0.0, feather=250.0):
    """Launch smoke along the bottom: overlapping puffs, each shaded on its lower right. Their tops
    stay below the line y = top, which rises by lift over focus = (x0, x1) - the rockets' bases - and
    falls back over feather pixels either side."""
    rnd = random.Random(seed)
    d = ImageDraw.Draw(im)
    items = []
    for i in range(puffs):
        x = rnd.uniform(-60, SIZE + 60)
        r = rnd.uniform(55, 110)
        k = 0.0
        if focus:
            k = max(0.0, 1 - max(focus[0] - x, x - focus[1], 0.0) / feather)
        line = top - lift * k
        r *= 1 + 0.3 * k
        items.append((line + r + rnd.uniform(0, 45) * (1 - 0.8 * k), x, r))
    for y, x, r in sorted(items):                          # back (higher) puffs first
        cx, cy, R = x * SS, y * SS, r * SS
        d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=SHADE)
        R2 = R * 0.9
        d.ellipse((cx - R2 - R * 0.12, cy - R2 - R * 0.12, cx + R2 - R * 0.12, cy + R2 - R * 0.12), fill=CREAM)
    if top + 110 < SIZE:
        d.rectangle((0, (top + 110) * SS, W, W), fill=CREAM)


def flame(im, cx, top, width, height):
    d = ImageDraw.Draw(im)
    for k, color in zip((1.0, 0.68, 0.36), reversed(FLAME)):
        w, h = width * k / 2, height * (0.55 + 0.45 * k)
        pts = [(cx - w, top), (cx + w, top)]
        steps = 16
        for i in range(steps + 1):                         # a rounded tongue down to the tip
            t = i / steps
            pts.append((cx + w * (1 - t) ** 0.7 * math.cos(t * math.pi / 2), top + h * math.sin(t * math.pi / 2)))
        pts.append((cx, top + h))
        for i in range(steps, -1, -1):
            t = i / steps
            pts.append((cx - w * (1 - t) ** 0.7 * math.cos(t * math.pi / 2), top + h * math.sin(t * math.pi / 2)))
        d.polygon([s(*p) for p in pts], fill=color)


def cutout(name, height=None, width=None):
    """A render, cropped to the model, mirrored the way the game shows models, scaled to fit (unscaled px)."""
    im = Image.open(os.path.join(CUTS, name + '.png')).convert('RGBA')
    im = im.crop(im.getchannel('A').getbbox()).transpose(Image.FLIP_LEFT_RIGHT)
    k = min((height or 1e9) * SS / im.height, (width or 1e9) * SS / im.width)
    return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)


def outline(im, px=5, color=INK):
    """The cut-out with a printed key line round it."""
    a = im.getchannel('A').filter(ImageFilter.MaxFilter(2 * px * SS + 1))
    out = Image.new('RGBA', (im.width, im.height), color + (0,))
    out.putalpha(a)
    out.alpha_composite(im)
    return out


def put(canvas, im, x, y, anchor='mb'):
    """Paste at unscaled (x, y): anchor 'mb' = middle of the bottom edge, 'mm' = centre."""
    X, Y = x * SS, y * SS
    X -= im.width / 2
    Y -= im.height if anchor == 'mb' else im.height / 2
    canvas.paste(im, (round(X), round(Y)), im)


def frame(im):
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W - 1, W - 1), outline=CREAM, width=18 * SS)
    d.rectangle(s(18, 18, SIZE - 19, SIZE - 19), outline=INK, width=4 * SS)


def finish(im, key):
    frame(im)
    im = paper(im.resize((SIZE, SIZE), Image.LANCZOS))
    os.makedirs(POSTERS, exist_ok=True)
    path = os.path.join(POSTERS, key + '.png')
    im.save(path, optimize=True)
    if os.path.getsize(path) >= 1000 * 1024:               # the game refuses previews of 1 MB or more
        im.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)
    print('%-11s %4d KB  %s' % (key, os.path.getsize(path) // 1024, os.path.relpath(path, ROOT)))
    return path


# ---------------------------------------------------------------- posters --

def rocket_poster(key):
    cut, title, cyr, year, tagline = ROCKETS[key]
    im = Image.new('RGB', (W, W), RED)
    sunburst(im, (720, 930), turn=0.05)
    vignette(im)
    rk = outline(cutout(cut, height=730, width=300))
    base = 800                                             # the whole rocket stands clear of the smoke
    flame(im, 720, base - 6, rk.width / SS * 0.6, 160)
    put(im, rk, 720, base)
    clouds(im, 935, 40, seed=sum(map(ord, key)), focus=(720, 720), lift=90)
    d = ImageDraw.Draw(im)
    star(d, (92, 92), 34, GOLD, outline=INK, width=3)
    text(d, (140, 52), 'SPACE RACE', font(40), fill=CREAM, offset=3)
    f = fit(title, 470, 190)
    text(d, (60, 120), title, f, offset=8)
    bottom = d.textbbox(s(60, 120), title, font=f)[3] / SS
    ribbon(d, (78, bottom + 34), cyr, fit(cyr, 420, 52, 'SemiBold'))
    badge(im, (175, 590), 92, year)
    text(d, (60, 712), tagline, font(54, 'SemiBold'), offset=4, spacing=4)
    return finish(im, key)


def sash(im, body):
    """A gold band across the top right corner."""
    f = font(46)
    band = Image.new('RGBA', (620 * SS, 92 * SS), GOLD + (255,))
    d = ImageDraw.Draw(band)
    d.rectangle((0, 0, band.width - 1, band.height - 1), outline=INK, width=5 * SS)
    d.text((band.width / 2, band.height / 2), body, font=f, fill=INK, anchor='mm')
    band = band.rotate(-45, expand=True, resample=Image.BICUBIC)
    put(im, band, SIZE - 150, 150, anchor='mm')


def package_poster(key='package', tagline='BEAT APOLLO 11\nTO THE MOON', banner=None):
    im = Image.new('RGB', (W, W), RED)
    sunburst(im, (620, 1100), rays=30, turn=0.02)
    vignette(im)
    d = ImageDraw.Draw(im)
    moon = (830, 190, 92) if not banner else (700, 150, 80)
    cx, cy, r = s(*moon)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CREAM, outline=INK, width=5 * SS)
    for dx, dy, rr in ((-30, -20, 18), (25, 30, 13), (32, -32, 9), (-18, 40, 10)):   # craters
        x, y, q = s(moon[0] + dx, moon[1] + dy, rr)
        d.ellipse((x - q, y - q, x + q, y + q), fill=SHADE)
    rk = outline(cutout('lineup', height=600, width=560))
    put(im, rk, 690, 862)
    clouds(im, 955, 48, seed=11, focus=(690 - rk.width / SS / 2, 690 + rk.width / SS / 2), lift=125, feather=140)
    d = ImageDraw.Draw(im)
    text(d, (52, 40), 'SPACE\nRACE', font(196), offset=9, spacing=-38)
    y = ribbon(d, (68, 482), 'КОСМИЧЕСКАЯ ГОНКА', font(40, 'SemiBold'))
    text(d, (56, y + 22), tagline, font(46, 'SemiBold'), offset=4, spacing=2)
    stamp(im, (178, 762), 86, ' SPACE RACE · МОД · 1957–1969 ·', '1.1.1.9')
    if banner:
        sash(im, banner)
    return finish(im, key)


def kit_poster():
    im = Image.new('RGB', (W, W), RED)
    sunburst(im, (512, 600), rays=28)
    vignette(im)
    # models first, lettering on top
    put(im, outline(cutout('b_pad_r7', height=500, width=740), px=4), SIZE / 2, 600, anchor='mm')
    put(im, outline(cutout('b_mik', height=200, width=380), px=4), 235, 985)
    put(im, outline(cutout('b_tracking', height=260, width=330), px=4), 805, 990)
    d = ImageDraw.Draw(im)
    star(d, (300, 64), 22, GOLD, outline=INK, width=2)
    star(d, (SIZE - 300, 64), 22, GOLD, outline=INK, width=2)
    text(d, (SIZE / 2, 42), 'SPACE RACE KIT', font(40), offset=3, anchor='ma')
    f = fit('COSMODROME', 880, 160)
    text(d, (SIZE / 2, 92), 'COSMODROME', f, offset=8, anchor='ma')
    bottom = d.textbbox(s(SIZE / 2, 92), 'COSMODROME', font=f, anchor='ma')[3] / SS
    label = 'КОСМОДРОМ · 16 ЗДАНИЙ'
    lf = font(44, 'SemiBold')
    lw = d.textbbox((0, 0), label, font=lf)[2] / SS
    ribbon(d, ((SIZE - lw) / 2, bottom + 24), label, lf)
    return finish(im, 'kit')


POSTER = {'package': package_poster, 'kit': kit_poster,
          # the Steam collection of every item (tools/workshop_upload.py collection); no item folder of its own
          'collection': lambda: package_poster('collection', 'THE COMPLETE\nPROGRAMME', banner='COLLECTION')}
POSTER.update((k, (lambda k=k: rocket_poster(k))) for k in ROCKETS)


def compose(keys=None):
    paths = {key: make() for key, make in POSTER.items() if not keys or key in keys}
    for key, path in paths.items():
        if key in TARGETS:
            shutil.copyfile(path, os.path.join(ROOT, TARGETS[key], 'previewimage.png'))
    sheet = Image.new('RGB', (3 * 520, 3 * 520), INK)
    for i, key in enumerate(list(paths)[:9]):
        sheet.paste(Image.open(paths[key]).convert('RGB').resize((512, 512), Image.LANCZOS), (4 + 520 * (i % 3), 4 + 520 * (i // 3)))
    sheet.save(os.path.join(POSTERS, '_sheet.png'))


def render():
    cmd = [BLENDER, '-b', '--python', os.path.join(ROOT, 'tools', 'space_thumb_scene.py'), '--',
           os.path.join(ROOT, 'build', 'space_textures'), os.path.join(ROOT, 'mod', 'buildings', 'space_kit'), CUTS]
    subprocess.run(cmd, check=True, cwd=ROOT)


if __name__ == '__main__':
    if sys.argv[1:2] != ['compose']:
        render()
    compose(set(sys.argv[2:]) or None)
