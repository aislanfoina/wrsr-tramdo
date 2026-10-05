"""The Tram Distribution Office on the Steam Workshop: one item with both tram yards and the plugin.

    python tools/tramdo_workshop.py           # workshopconfig.ini + previewimage.png -> mod/packages/tram_do
    python tools/tramdo_workshop.py poster    # only the poster (build/tramdo/poster.png and the preview)

  tram_do   tramdo_small, tramdo_large (tools/tramdo_scene.py) + the tramdo plugin   WORKSHOP_ITEMTYPE_BUILDING

build.ps1 -Install copies mod/packages/tram_do to workshop_wip/<id> and puts the plugin (its
package.txt names tram_do) into the item's plugins/ folder; RML loads plugins from there like from
any Workshop item. The poster needs build/tramdo/tramdo_large_cut.png (tools/tramdo_scene.py) and
the Space Race poster helpers (tools/space_thumbs.py).

Publishing: tools/workshop_upload.py tram_do create (prints the Steam id - put it in ITEMS), rebuild,
install, then upload content/preview/description. $VISIBILITY is the game's numbering: 0 unpublished,
1 friends only, 2 PUBLIC.
"""
import os
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
OWNER = 76561198165729857
VISIBILITY = 0                  # unpublished until checked in game
REPO = 'https://github.com/aislanfoina/wrsr-tramdo'
IMAGES = REPO.replace('https://github.com/', 'https://raw.githubusercontent.com/') + '/main/docs/images/'
RML = 'https://steamcommunity.com/sharedfiles/filedetails/?id=3787969749'
CARGO_TRAMS = 'https://steamcommunity.com/workshop/filedetails/?id=3586298879'
ITEM_URL = 'https://steamcommunity.com/sharedfiles/filedetails/?id=%d'
PREVIEWS = os.path.join(ROOT, 'build', 'tramdo')

# key: (folder, item id, item type, name). A local development id until the item exists on Steam.
ITEMS = {
    'tram_do': ('mod/packages/tram_do', 9000310, 'WORKSHOP_ITEMTYPE_BUILDING', 'Tram Distribution Office [1.1.1.9]'),
}
OBJECTS = {'tram_do': ['tramdo_small', 'tramdo_large']}
REQUIRED = {'tram_do': [3787969749]}

FOOTER = '''[h2]LICENCE AND CREDITS[/h2]
GPL-3.0, source code on GitHub: [url=%(repo)s]%(repo)s[/url]. The plugin builds against TesmioLoader by MaxLegend and runs on [url=%(rml)s]Republic Mod Loader[/url] by UltimateUniverse. The cargo trams themselves come from other authors' mods; this office only runs them.

Workers & Resources: Soviet Republic is (c) 3Division. This is an independent fan-made mod, not affiliated with or endorsed by 3Division or Hooded Horse.''' % {'repo': REPO, 'rml': RML}

PAGE = '''[h1]COMRADE, THE TRAMS WILL NOW RUN TO PLAN.[/h1]
Your cargo trams have stood in the depot long enough, waiting for someone to tell them where to go. The Ministry of Municipal Transport has opened a dispatch office.

[img]%(img)syard_large.jpg[/img]

[b]Tram Distribution Office[/b] does for cargo trams what the game's distribution offices do for trucks and trains: it buys and keeps the trams, takes loading and unloading stations as tasks, and sends a tram whenever a station has goods to move, with no fixed routes to set.

[h2]TWO YARDS[/h2]
[list]
[*][b]Tram Distribution Office (small trams)[/b]: the game's small tram depot layout, four parking lanes, room for %(small)d vehicles. Takes cargo tram sets up to [b]30 m[/b] (the small and medium sets).
[*][b]Tram Distribution Office (large trams)[/b]: the same yard with lanes half as long again for the long sets, room for %(large)d vehicles. Takes every cargo tram.
[/list]
Both have a brick tram shed, the ТРАМГРУЗ dispatch wing, a traction substation and a sand tower. The game lays the yard's track and trolley wire itself, as with its own depots.

[h2]HOW TO RUN IT[/h2]
[olist]
[*]Subscribe to this item and to [url=%(rml)s]Republic Mod Loader[/url]. You also need cargo trams, for example the [url=%(trams)s]cargo tram collection[/url] this office was built and tested with.
[*]Run Republic Mod Loader, enable this item and its [b]tramdo[/b] plugin, and launch.
[*]Build the office on your tram network, buy cargo trams in its window (or move trams in), and give it tasks like any distribution office: the tram cargo stations to load at and to unload at.
[/olist]
Requires Workers & Resources: Soviet Republic [b]1.1.1.9[/b]: the plugin patches this exact build.

[h2]GOOD TO KNOW[/h2]
[list]
[*]Cargo trams only: passenger trams stay with the tram depot.
[*]Every wagon of a tram set takes one place in the office.
[*]Gravel, fluids and other bulk goods leave an unloading tram station by conveyor or pipe. Run the conveyor [b]straight into the storage[/b]: with a conveyor transfer building in between, the office sees the transfer as full and keeps the trams at home. The yellow 'unsupported with unloading' note on such stations can be ignored.
[*]Station thresholds work as with trucks: a station set to dispatch only at 20%% gets no tram before that.
[*]The plugin runs the office's planning with fuel off (trams are electric, the game's office would wait forever to refuel them) and lets only cargo trams in. Without the plugin the offices take no trams at all.
[/list]

[h2]STATUS[/h2]
Tested with open, covered, aggregate and waste trams. Fluid trams should work the same way but have not been tried yet. Reports are welcome on GitHub or below.

'''


def descriptions():
    return {'tram_do': PAGE % {'img': IMAGES, 'rml': RML, 'trams': CARGO_TRAMS, 'small': 24, 'large': 40} + FOOTER}


def workshop_items():
    """The items as tools/workshop_upload.py reads them: key, Steam id, game item type, title,
    store page text, the game's visibility value and Required Items (Steam ids)."""
    descs = descriptions()
    return [{'key': k, 'id': v[1], 'type': v[2], 'title': v[3], 'description': descs[k], 'visibility': VISIBILITY,
             'required': [ITEMS[r][1] if r in ITEMS else r for r in REQUIRED.get(k, [])]} for k, v in ITEMS.items()]


def config(key, desc):
    folder, item, typ, name = ITEMS[key]
    assert len(desc) < 8000, '%s: Steam descriptions stop at 8000 characters (%d)' % (key, len(desc))
    assert '"' not in desc, '%s: no double quotes inside $ITEM_DESC' % key
    lines = ['$ITEM_ID %d' % item, '', '$OWNER_ID %d' % OWNER, '', '$ITEM_TYPE %s' % typ, '', '$VISIBILITY %d' % VISIBILITY, '']
    lines += ['$OBJECT_BUILDING %s' % o for o in OBJECTS[key]] + ['']
    lines += ['$ITEM_NAME "%s"' % name, '', '$ITEM_DESC "%s"' % desc.replace('\n', '\r\n'), '', '$END', '']
    path = os.path.join(ROOT, folder, 'workshopconfig.ini')
    open(path, 'w', encoding='utf-8', newline='').write('\r\n'.join(lines))
    print('%-8s %d  %-36s %5d chars  %s' % (key, item, name, len(desc), os.path.relpath(path, ROOT)))


# ---------------------------------------------------------------- poster --

def poster():
    """Soviet-poster preview in the Space Race style: the large yard on a red sunburst."""
    import space_thumbs as T
    im = Image.new('RGB', (T.W, T.W), T.RED)
    T.sunburst(im, (512, 760), rays=28, turn=0.03)
    T.vignette(im)
    cut = Image.open(os.path.join(PREVIEWS, 'tramdo_large_cut.png')).convert('RGBA')
    cut = cut.crop(cut.getchannel('A').getbbox()).transpose(Image.FLIP_LEFT_RIGHT)   # as the game shows it
    k = min(980 * T.SS / cut.width, 560 * T.SS / cut.height)
    cut = cut.resize((round(cut.width * k), round(cut.height * k)), Image.LANCZOS)
    T.put(im, T.outline(cut, px=4), T.SIZE / 2, 990)
    d = ImageDraw.Draw(im)
    T.star(d, (232, 64), 22, T.GOLD, outline=T.INK, width=2)
    T.star(d, (T.SIZE - 232, 64), 22, T.GOLD, outline=T.INK, width=2)
    T.text(d, (T.SIZE / 2, 42), 'TRAM DISTRIBUTION OFFICE', T.font(40), offset=3, anchor='ma')
    f = T.fit('ТРАМГРУЗ', 860, 170)
    T.text(d, (T.SIZE / 2, 92), 'ТРАМГРУЗ', f, offset=8, anchor='ma')
    bottom = d.textbbox(T.s(T.SIZE / 2, 92), 'ТРАМГРУЗ', font=f, anchor='ma')[3] / T.SS
    label = 'CARGO TRAMS · DISPATCHED TO PLAN'
    lf = T.font(42, 'SemiBold')
    lw = d.textbbox((0, 0), label, font=lf)[2] / T.SS
    T.ribbon(d, ((T.SIZE - lw) / 2, bottom + 24), label, lf)
    T.stamp(im, (T.SIZE - 150, 545), 78, ' TRAM DO · МОД · 2 YARDS ·', '1.1.1.9')
    T.frame(im)
    im = T.paper(im.resize((T.SIZE, T.SIZE), Image.LANCZOS))
    path = os.path.join(PREVIEWS, 'poster.png')
    im.save(path, optimize=True)
    if os.path.getsize(path) >= 1000 * 1024:               # the game refuses previews of 1 MB or more
        im.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)
    shutil.copyfile(path, os.path.join(ROOT, ITEMS['tram_do'][0], 'previewimage.png'))
    print('poster   %4d KB  %s' % (os.path.getsize(path) // 1024, os.path.relpath(path, ROOT)))


def main():
    if sys.argv[1:2] == ['poster']:
        return poster()
    descs = descriptions()
    for key in ITEMS:
        config(key, descs[key])
    poster()


if __name__ == '__main__':
    main()
