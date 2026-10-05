"""Build every Tram Distribution Office asset: textures, the two yards, the item and its poster, the README images.

    python tools/build_tramdo.py              # textures yards item images
    python tools/build_tramdo.py yards item   # one or more stages

Stages:
  textures  the shared kit textures (tools/space_textures.py) -> build/space_textures
  yards     both yards in Blender (tools/tramdo_scene.py) -> mod/packages/tram_do, previews in build/tramdo
  item      workshopconfig.ini and the poster / previewimage.png (tools/tramdo_workshop.py)
  images    the README and store page pictures -> docs/images

Then build.ps1 -Install (game and loader closed) compiles the plugin and installs the item with it.
Needs Blender 5.x (set BLENDER if it is not in its default folder), Pillow and numpy.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = os.environ.get('BLENDER', r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')
PY = sys.executable
TEX = 'build/space_textures'
ITEM = 'mod/packages/tram_do'
PREVIEW = 'build/tramdo'
IMAGES = 'docs/images'


def run(cmd):
    print('>', ' '.join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        sys.exit('failed: %s' % cmd[0])


def stage_textures():
    run([PY, 'tools/space_textures.py', TEX])


def stage_yards():
    run([BLENDER, '-b', '--python', 'tools/tramdo_scene.py', '--', TEX, ITEM, PREVIEW])


def stage_item():
    run([PY, 'tools/tramdo_workshop.py'])


def stage_images():
    from PIL import Image
    out = os.path.join(ROOT, IMAGES)
    os.makedirs(out, exist_ok=True)
    for src, dst in (('tramdo_large.png', 'yard_large.jpg'), ('tramdo_small.png', 'yard_small.jpg'),
                     ('tramdo_small_top.png', 'yard_plan.jpg'), ('poster.png', 'poster.jpg')):
        im = Image.open(os.path.join(ROOT, PREVIEW, src)).convert('RGB')
        if src != 'poster.png':                            # the game shows models mirrored; so do these
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        im.save(os.path.join(out, dst), quality=88, optimize=True)
        print('%-14s %4d KB' % (dst, os.path.getsize(os.path.join(out, dst)) // 1024))


STAGES = {'textures': stage_textures, 'yards': stage_yards, 'item': stage_item, 'images': stage_images}

if __name__ == '__main__':
    for name in [a for a in sys.argv[1:] if a in STAGES] or list(STAGES):
        STAGES[name]()
