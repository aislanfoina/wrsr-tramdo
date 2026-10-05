"""Drive the running game window: force it to the foreground (Alt trick), capture
the primary monitor scaled, crop regions at full resolution, click, keys, text.
    python tools/dev/gdrive.py fg
    python tools/dev/gdrive.py shot out.png [scale]
    python tools/dev/gdrive.py crop x0 y0 x1 y1 out.png [scale]
    python tools/dev/gdrive.py click X Y [right|double]
    python tools/dev/gdrive.py move X Y
    python tools/dev/gdrive.py key ESC|ENTER|...   (space separated list)
    python tools/dev/gdrive.py type "text"
    python tools/dev/gdrive.py wheel X Y N
Coordinates are physical pixels of the primary monitor (5120x1440)."""
import ctypes, ctypes.wintypes as w, subprocess, sys, time
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()
u = ctypes.windll.user32
VK = {'ESC': 0x1B, 'ENTER': 0x0D, 'TAB': 0x09, 'SPACE': 0x20, 'BACK': 0x08, 'DEL': 0x2E, 'F1': 0x70, 'F5': 0x74, 'F9': 0x78, 'F11': 0x7A,
      'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27, 'PGUP': 0x21, 'PGDN': 0x22, 'HOME': 0x24, 'END': 0x23, 'ALT': 0x12, 'CTRL': 0x11, 'SHIFT': 0x10}


def game_hwnd():
    out = subprocess.run(['tasklist', '/fi', 'imagename eq SOVIET64.exe', '/fo', 'csv', '/nh'], capture_output=True, text=True).stdout
    pids = [int(l.split('","')[1]) for l in out.splitlines() if 'SOVIET64' in l]
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def cb(h, l):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, buf, 256)
            if 'Soviet' in buf.value:
                found.append(h)
        return True
    u.EnumWindows(cb, 0)
    return found[0] if found else 0


def fg():
    h = game_hwnd()
    if not h:
        print('no game window'); return 0
    if u.GetForegroundWindow() == h:
        return h
    u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)   # Alt tap unlocks SetForegroundWindow
    u.ShowWindow(h, 9)
    u.SetForegroundWindow(h)
    time.sleep(0.6)
    print('foreground', u.GetForegroundWindow() == h)
    return h


def grab():
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=(0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)), all_screens=True)


def click(x, y, kind='left'):
    u.SetCursorPos(int(x), int(y)); time.sleep(0.15)
    if kind == 'right':
        u.mouse_event(8, 0, 0, 0, 0); time.sleep(0.06); u.mouse_event(16, 0, 0, 0, 0)
    else:
        n = 2 if kind == 'double' else 1
        for _ in range(n):
            u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.06); u.mouse_event(4, 0, 0, 0, 0); time.sleep(0.08)


def key(name):
    vk = VK.get(name.upper())
    if vk is None:
        vk = u.VkKeyScanW(ord(name)) & 0xFF
    u.keybd_event(vk, 0, 0, 0); time.sleep(0.05); u.keybd_event(vk, 0, 2, 0); time.sleep(0.05)


class _KI(ctypes.Structure):
    _fields_ = [('wVk', w.WORD), ('wScan', w.WORD), ('dwFlags', w.DWORD), ('time', w.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', _KI), ('pad', ctypes.c_byte * 32)]
    _anonymous_ = ('u',)
    _fields_ = [('type', w.DWORD), ('u', _U)]


def hold(name, secs):
    """press a key by SCAN CODE for `secs` seconds; the game reads the keyboard through DirectInput,
    which ignores keybd_event calls that carry only a virtual key"""
    vk = VK.get(name.upper())
    if vk is None:
        vk = u.VkKeyScanW(ord(name)) & 0xFF
    scan = u.MapVirtualKeyW(vk, 0)
    down = _INPUT(type=1); down.ki = _KI(0, scan, 0x0008, 0, None)
    up = _INPUT(type=1); up.ki = _KI(0, scan, 0x0008 | 0x0002, 0, None)
    u.SendInput(1, ctypes.byref(down), ctypes.sizeof(_INPUT))
    time.sleep(secs)
    u.SendInput(1, ctypes.byref(up), ctypes.sizeof(_INPUT))


def type_text(s):
    for ch in s:
        u.keybd_event(0, 0, 4, ord(ch)); u.keybd_event(0, 0, 6, ord(ch)); time.sleep(0.03)   # KEYEVENTF_UNICODE


if __name__ == '__main__':
    a = sys.argv[1:]
    cmd = a[0]
    if cmd == 'fg':
        fg()
    elif cmd == 'shot':
        fg(); time.sleep(0.4); im = grab(); sc = float(a[2]) if len(a) > 2 else 0.35
        im.resize((int(im.size[0] * sc), int(im.size[1] * sc))).save(a[1]); print('saved', a[1], im.size, 'scale', sc)
    elif cmd == 'crop':
        fg(); time.sleep(0.4); im = grab().crop(tuple(int(v) for v in a[1:5])); sc = float(a[6]) if len(a) > 6 else 1.0
        if sc != 1.0: im = im.resize((int(im.size[0] * sc), int(im.size[1] * sc)))
        im.save(a[5]); print('saved', a[5], im.size)
    elif cmd == 'click':
        fg(); click(a[1], a[2], a[3] if len(a) > 3 else 'left'); print('clicked', a[1], a[2])
    elif cmd == 'move':
        fg(); u.SetCursorPos(int(a[1]), int(a[2]))
    elif cmd == 'key':
        fg()
        for k in a[1:]: key(k)
        print('keys', a[1:])
    elif cmd == 'type':
        fg(); type_text(a[1]); print('typed', a[1])
    elif cmd == 'hold':          # hold KEY secs - by scan code, which the game's DirectInput sees (plain `key` is ignored in game)
        fg(); hold(a[1], float(a[2]) if len(a) > 2 else 0.12); print('held', a[1])
    elif cmd == 'stype':         # stype "text" - letters/digits/space as scan-code key presses (in-game text boxes ignore `type`)
        fg()
        for ch in a[1]:
            hold('SPACE' if ch == ' ' else ch, 0.04); time.sleep(0.04)
        print('stype', a[1])
    elif cmd == 'mhold':         # mhold X Y secs - left button held, e.g. "hold LMB to flatten terrain"
        fg(); u.SetCursorPos(int(a[1]), int(a[2])); time.sleep(0.15)
        u.mouse_event(2, 0, 0, 0, 0); time.sleep(float(a[3]) if len(a) > 3 else 1.0); u.mouse_event(4, 0, 0, 0, 0)
        print('held LMB at', a[1], a[2])
    elif cmd == 'wheel':
        fg(); u.SetCursorPos(int(a[1]), int(a[2])); time.sleep(0.1); u.mouse_event(0x800, 0, 0, int(a[3]) * 120, 0); print('wheel', a[3])
