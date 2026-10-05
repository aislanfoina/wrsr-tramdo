"""Start Republic Mod Loader if needed and press its "Launch Workers & Resources"
button without stealing the foreground: the loader window is captured with
PrintWindow (works while covered or minimised), the big red button is found by
colour, and the click is posted straight to the window (WM_LBUTTONDOWN/UP at
the button's client position). Then waits for SOVIET64.exe.
    python tools/dev/rml_launch.py
"""
import ctypes
import ctypes.wintypes as w
import subprocess
import sys
import time

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass
u = ctypes.windll.user32
g = ctypes.windll.gdi32
RML_DIR = r'C:\Program Files (x86)\Steam\steamapps\workshop\content\784150\3787969749'


class BMI(ctypes.Structure):
    _fields_ = [('biSize', w.DWORD), ('biWidth', w.LONG), ('biHeight', w.LONG), ('biPlanes', w.WORD), ('biBitCount', w.WORD),
                ('biCompression', w.DWORD), ('biSizeImage', w.DWORD), ('x', w.LONG), ('y', w.LONG), ('c', w.DWORD), ('i', w.DWORD)]


def game_running():
    out = subprocess.run(['tasklist', '/fi', 'imagename eq SOVIET64.exe', '/nh'], capture_output=True, text=True).stdout
    return 'SOVIET64' in out


def capture(h):
    from PIL import Image
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    W, H = r.right - r.left, r.bottom - r.top
    hdc = u.GetDC(0)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, W, H)
    g.SelectObject(mdc, bmp)
    u.PrintWindow(h, mdc, 2)
    bi = BMI()
    bi.biSize = ctypes.sizeof(BMI)
    bi.biWidth = W
    bi.biHeight = -H
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(W * H * 4)
    g.GetDIBits(mdc, bmp, 0, H, buf, ctypes.byref(bi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(0, hdc)
    return Image.frombuffer('RGBA', (W, H), buf.raw, 'raw', 'BGRA', 0, 1).convert('RGB'), r


def find_launch_button(im):
    """the launch button is the largest saturated-red block in the lower half of the window"""
    import numpy as np
    a = np.asarray(im).astype(int)
    red = (a[:, :, 0] > 170) & (a[:, :, 1] < 120) & (a[:, :, 2] < 120)
    H = red.shape[0]
    red[: H // 2] = False
    rows = red.sum(axis=1)
    ys = [y for y in range(H) if rows[y] > 150]
    if not ys:
        return None
    y0, y1 = min(ys), max(ys)
    cols = red[y0:y1 + 1].sum(axis=0)
    xs = [x for x in range(red.shape[1]) if cols[x] > (y1 - y0) * 0.5]
    if not xs:
        return None
    return (min(xs) + max(xs)) // 2, (y0 + y1) // 2


def main():
    if game_running():
        print('game already running')
        return 0
    h = u.FindWindowW(None, 'Republic Mod Loader')
    if not h:
        subprocess.Popen([RML_DIR + r'\RepublicModLoader.exe'], cwd=RML_DIR)
        for _ in range(40):
            time.sleep(1)
            h = u.FindWindowW(None, 'Republic Mod Loader')
            if h:
                break
        time.sleep(8)      # let it finish scanning the plugins and dev items
    if not h:
        print('no loader window')
        return 1
    u.ShowWindow(h, 9)
    time.sleep(0.8)
    im, r = capture(h)
    im.save('build/rml_win.png')
    hit = find_launch_button(im)
    if not hit:
        print('launch button not found in the loader window (build/rml_win.png)')
        return 1
    print('window %dx%d, launch button at %s' % (im.size[0], im.size[1], hit))
    pt = w.POINT(r.left + hit[0], r.top + hit[1])
    u.ScreenToClient(h, ctypes.byref(pt))
    lp = (pt.y << 16) | (pt.x & 0xFFFF)
    u.PostMessageW(h, 0x200, 0, lp)
    time.sleep(0.1)
    u.PostMessageW(h, 0x201, 1, lp)
    time.sleep(0.08)
    u.PostMessageW(h, 0x202, 0, lp)
    for i in range(25):
        time.sleep(1)
        if game_running():
            print('game started after %d s' % (i + 1))
            return 0
    print('no game process after 25 s')
    return 1


if __name__ == '__main__':
    sys.exit(main())
