"""Manage the mods' Steam Workshop items without the game, through the Steam client you are signed in to.

    python tools/workshop_upload.py space_race --check                        # nothing is sent: sign-in, items, differences
    python tools/workshop_upload.py space_race preview description            # push those fields for every item
    python tools/workshop_upload.py space_race content --only kit,sr_n1 --note "Fix the N1 pad"
    python tools/workshop_upload.py space_race required                       # Required Items on the main item
    python tools/workshop_upload.py republic_in_ruins create --only words     # new items; prints their ids
    python tools/workshop_upload.py space_race collection                     # the collection of all items

Mods: space_race (tools/space_workshop.py), republic_in_ruins (tools/yearzero_workshop.py), tram_do
(tools/tramdo_workshop.py); each
packer's workshop_items() is the source of truth for ids, titles, store pages, visibility and
Required Items.

Fields (several at once, or all):
  title        the packer's item name
  description  the packer's store page text (Steam BBCode)
  preview      previewimage.png of the installed item, media_soviet/workshop_wip/<id> (under 1 MB)
  content      that installed folder itself - run build.ps1 -Install first, with the game and RML closed
  visibility   the packer's $VISIBILITY, in the game's numbering (0 unpublished, 1 friends, 2 public)
Actions:
  required     add the packer's Required Items (existing ones stay)
  create       create the items that still have local ids (9000xxx) with the game's type tag,
               private; put the printed ids in the packer, rebuild, install, then upload content
  collection   the packer's workshop_collection(): created on first use (put the printed id in the
               packer), then its page is set and its items added - "Subscribe to all" for players
  --check      sign-in, ids and what differs from the live store pages; touches nothing on Steam

It loads the game's own steam_api64.dll (Steamworks flat API, ISteamUGC v012) as app 784150, so
Steam must be running and signed in to the account that owns the items; no password is involved,
and Steam shows that account as playing the game while this runs. Like the game, it must run
outside any sandbox: from a sandboxed shell (an AI agent's) SteamAPI_Init fails. Each update is
checked afterwards against Steam's public GetPublishedFileDetails.
"""
import argparse
import ctypes
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from ctypes import POINTER, Structure, byref, c_bool, c_char_p, c_int, c_uint32, c_uint64, c_void_p

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
GAME = os.environ.get('WRSR_GAME', r'C:\Program Files (x86)\Steam\steamapps\common\SovietRepublic')
WIP = os.path.join(GAME, 'media_soviet', 'workshop_wip')
APP = 784150
MODS = {'space_race': 'space_workshop', 'republic_in_ruins': 'yearzero_workshop', 'tram_do': 'tramdo_workshop'}
FIELDS = ('title', 'description', 'preview', 'content', 'visibility')
ACTIONS = ('required', 'create', 'collection')

# the tag the game gives each item type on Steam (its in-game browser filters by it)
TYPE_TAG = {'WORKSHOP_ITEMTYPE_SCRIPT': 'Script', 'WORKSHOP_ITEMTYPE_BUILDING': 'Building',
            'WORKSHOP_ITEMTYPE_VEHICLE': 'Vehicle', 'WORKSHOP_ITEMTYPE_TEXT': 'Text modification',
            'WORKSHOP_ITEMTYPE_LANDSCAPE': 'Landscape', 'WORKSHOP_ITEMTYPE_BUILDINGSKIN': 'Building skin',
            'WORKSHOP_ITEMTYPE_VEHICLESKIN': 'Vehicle skin', 'WORKSHOP_ITEMTYPE_BUILDINGEDITOR_ELEMENT': 'Building editor element'}
# workshopconfig.ini's $VISIBILITY is the game's numbering; Steam's is 0 public, 1 friends only, 2 private
STEAM_VISIBILITY = {0: 2, 1: 1, 2: 0}
VISIBILITY_NAME = {0: 'public', 1: 'friends only', 2: 'private', 3: 'unlisted'}
ERESULT = {1: 'OK', 2: 'Fail', 8: 'InvalidParam', 9: 'FileNotFound', 15: 'AccessDenied', 16: 'Timeout',
           25: 'LimitExceeded', 29: 'DuplicateRequest', 33: 'Busy'}
UPDATE_STATUS = {1: 'preparing config', 2: 'preparing content', 3: 'uploading content', 4: 'uploading preview',
                 5: 'committing changes'}
CB_CREATE, CB_SUBMIT, CB_DEPENDENCY = 3403, 3404, 3412          # k_iClientUGCCallbacks + 3 / 4 / 12


# ------------------------------------------------------------- the items --

def items(mod, only):
    packer = importlib.import_module(MODS[mod])
    out = packer.workshop_items()
    if only:
        keys = set(only.split(','))
        unknown = keys - {i['key'] for i in out}
        if unknown:
            sys.exit('unknown item(s) %s; %s has %s' % (', '.join(sorted(unknown)), mod, ', '.join(i['key'] for i in out)))
        out = [i for i in out if i['key'] in keys]
    return packer, out


def on_steam(item):
    return item['id'] > 100000000                                # local development ids are 9000xxx


def folder(item):
    return os.path.join(WIP, str(item['id']))


def generated(path):
    """Files the plugins write into their own item folder while the game runs: never upload them."""
    out = []
    for base, _dirs, files in os.walk(path):
        rel = os.path.relpath(base, path)
        for f in files:
            if f.endswith('.log') or f == 'research_merged.ini' or rel.replace('\\', '/').endswith('spacerace_data/buildings'):
                out.append(os.path.join(rel, f))
    return out


def game_running():
    out = subprocess.run(['tasklist'], capture_output=True, text=True).stdout.lower()
    return [p for p in ('soviet64.exe', 'republicmodloader.exe') if p in out]


def problems(item, fields):
    """What stops an upload of these fields, before anything is sent."""
    out = []
    if not on_steam(item):
        out.append('not on Steam yet (local id %d): create it first' % item['id'])
        return out
    if 'title' in fields and len(item['title'].encode('utf-8')) > 128:
        out.append('title longer than 128 bytes')
    if 'description' in fields and len(item['description']) >= 8000:
        out.append('description %d characters, Steam stops at 8000' % len(item['description']))
    if 'preview' in fields or 'content' in fields:
        cfg = os.path.join(folder(item), 'workshopconfig.ini')
        if not os.path.exists(cfg):
            out.append('not installed: %s (run build.ps1 -Install)' % folder(item))
            return out
        ids = [line.split()[1] for line in open(cfg, encoding='utf-8', errors='replace') if line.startswith('$ITEM_ID')]
        if ids != [str(item['id'])]:
            out.append('%s says $ITEM_ID %s' % (cfg, ids))
    if 'preview' in fields:
        png = os.path.join(folder(item), 'previewimage.png')
        if not os.path.exists(png):
            out.append('no previewimage.png')
        elif os.path.getsize(png) >= 1 << 20:
            out.append('previewimage.png is %d KB; Steam and the game want under 1 MB' % (os.path.getsize(png) // 1024))
    if 'content' in fields:
        junk = generated(folder(item))
        if junk:
            out.append('generated files in the folder (%s...): re-run build.ps1 -Install with the game closed' % junk[0])
    return out


def live(ids):
    """The public store data per id (Steam's GetPublishedFileDetails; private items come back empty)."""
    ids = [i for i in ids if i > 100000000]
    if not ids:
        return {}
    data = {'itemcount': len(ids)}
    for n, i in enumerate(ids):
        data['publishedfileids[%d]' % n] = i
    req = urllib.request.Request('https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/',
                                 data=urllib.parse.urlencode(data).encode())
    try:
        r = json.load(urllib.request.urlopen(req, timeout=30))
    except OSError as e:
        print('(public item data unavailable: %s)' % e)
        return {}
    return {int(d['publishedfileid']): d for d in r['response']['publishedfiledetails'] if d.get('result') == 1}


# ----------------------------------------------------------------- Steam --

class Strings(Structure):
    _fields_ = [('strings', POINTER(c_char_p)), ('count', c_int)]


SIGNATURES = {
    'SteamAPI_Init': (c_bool, []), 'SteamAPI_Shutdown': (None, []), 'SteamAPI_RunCallbacks': (None, []),
    'SteamClient': (c_void_p, []), 'SteamAPI_GetHSteamUser': (c_int, []), 'SteamAPI_GetHSteamPipe': (c_int, []),
    'SteamInternal_FindOrCreateUserInterface': (c_void_p, [c_int, c_char_p]),
    'SteamInternal_CreateInterface': (c_void_p, [c_char_p]),
    'SteamAPI_ISteamClient_GetISteamUGC': (c_void_p, [c_void_p, c_int, c_int, c_char_p]),
    'SteamAPI_ISteamClient_GetISteamUtils': (c_void_p, [c_void_p, c_int, c_char_p]),
    'SteamAPI_ISteamClient_GetISteamUser': (c_void_p, [c_void_p, c_int, c_int, c_char_p]),
    'SteamAPI_ISteamUser_GetSteamID': (c_uint64, [c_void_p]),
    'SteamAPI_ISteamUGC_CreateItem': (c_uint64, [c_void_p, c_uint32, c_int]),
    'SteamAPI_ISteamUGC_StartItemUpdate': (c_uint64, [c_void_p, c_uint32, c_uint64]),
    'SteamAPI_ISteamUGC_SetItemTitle': (c_bool, [c_void_p, c_uint64, c_char_p]),
    'SteamAPI_ISteamUGC_SetItemDescription': (c_bool, [c_void_p, c_uint64, c_char_p]),
    'SteamAPI_ISteamUGC_SetItemPreview': (c_bool, [c_void_p, c_uint64, c_char_p]),
    'SteamAPI_ISteamUGC_SetItemContent': (c_bool, [c_void_p, c_uint64, c_char_p]),
    'SteamAPI_ISteamUGC_SetItemVisibility': (c_bool, [c_void_p, c_uint64, c_int]),
    'SteamAPI_ISteamUGC_SetItemTags': (c_bool, [c_void_p, c_uint64, POINTER(Strings)]),
    'SteamAPI_ISteamUGC_SubmitItemUpdate': (c_uint64, [c_void_p, c_uint64, c_char_p]),
    'SteamAPI_ISteamUGC_GetItemUpdateProgress': (c_int, [c_void_p, c_uint64, POINTER(c_uint64), POINTER(c_uint64)]),
    'SteamAPI_ISteamUGC_AddDependency': (c_uint64, [c_void_p, c_uint64, c_uint64]),
    'SteamAPI_ISteamUtils_IsAPICallCompleted': (c_bool, [c_void_p, c_uint64, POINTER(c_bool)]),
    'SteamAPI_ISteamUtils_GetAPICallResult': (c_bool, [c_void_p, c_uint64, c_void_p, c_int, c_int, POINTER(c_bool)]),
    'SteamAPI_ISteamUtils_GetAPICallFailureReason': (c_int, [c_void_p, c_uint64]),
}


class Steam:
    def __init__(self):
        os.environ['SteamAppId'] = os.environ['SteamGameId'] = str(APP)
        dll = os.path.join(GAME, 'steam_api64.dll')
        if not os.path.exists(dll):
            sys.exit('no %s (set WRSR_GAME to the game folder)' % dll)
        self.api = ctypes.CDLL(dll)
        for name, (res, args) in SIGNATURES.items():
            fn = getattr(self.api, name)
            fn.restype, fn.argtypes = res, args
        # this Steamworks version may look for steam_appid.txt in the working directory rather than the variable
        appdir = os.path.join(ROOT, 'build', 'steam')
        os.makedirs(appdir, exist_ok=True)
        open(os.path.join(appdir, 'steam_appid.txt'), 'w').write(str(APP))
        here = os.getcwd()
        os.chdir(appdir)
        try:
            ok = self.api.SteamAPI_Init()
        finally:
            os.chdir(here)
        if not ok:
            sys.exit('SteamAPI_Init failed. Steam must be running and signed in to the account that owns the game, and\n'
                     'this must run outside any sandbox (an AI agent\'s sandboxed shell cannot reach the Steam client).')
        user, pipe = self.api.SteamAPI_GetHSteamUser(), self.api.SteamAPI_GetHSteamPipe()
        self.route = {}
        self.ugc = self.interface('STEAMUGC_INTERFACE_VERSION012', user, pipe, 'GetISteamUGC')
        self.utils = self.interface('SteamUtils009', user, pipe, 'GetISteamUtils')
        su = self.interface('SteamUser020', user, pipe, 'GetISteamUser')
        missing = [v for v, p in (('ISteamUGC v012', self.ugc), ('SteamUtils009', self.utils), ('SteamUser020', su)) if not p]
        if missing:
            sys.exit('Steam signed in (user %d, pipe %d) but would not hand out %s' % (user, pipe, ', '.join(missing)))
        self.steamid = self.api.SteamAPI_ISteamUser_GetSteamID(su)

    def interface(self, version, user, pipe, getter):
        """An interface pointer: the SDK's own accessor route first (what the game's inline SteamUGC() etc.
        use), then ISteamClient's getters on the client versions this steam_api64.dll knows."""
        v = version.encode()
        p = self.api.SteamInternal_FindOrCreateUserInterface(user, v)
        if p:
            self.route[version] = 'FindOrCreateUserInterface'
            return p
        for name in ('SteamClient018', 'SteamClient017', None):
            client = self.api.SteamInternal_CreateInterface(name.encode()) if name else self.api.SteamClient()
            if not client:
                continue
            fn = getattr(self.api, 'SteamAPI_ISteamClient_' + getter)
            p = fn(client, pipe, v) if getter == 'GetISteamUtils' else fn(client, user, pipe, v)
            if p:
                self.route[version] = '%s.%s' % (name or 'SteamClient()', getter)
                return p
        return None

    def close(self):
        self.api.SteamAPI_Shutdown()

    def wait(self, call, callback, sizes, handle=None, timeout=3600):
        """Waits for an API call and returns its result struct's bytes."""
        failed = c_bool()
        start, shown = time.time(), None
        while not self.api.SteamAPI_ISteamUtils_IsAPICallCompleted(self.utils, call, byref(failed)):
            self.api.SteamAPI_RunCallbacks()
            if handle is not None:
                done, total = c_uint64(), c_uint64()
                status = self.api.SteamAPI_ISteamUGC_GetItemUpdateProgress(self.ugc, handle, byref(done), byref(total))
                line = UPDATE_STATUS.get(status, '')
                if line and total.value:
                    line += ' %d%%' % (100 * done.value // total.value)
                if line and line != shown:
                    print('    ' + line, flush=True)
                    shown = line
            if time.time() - start > timeout:
                sys.exit('Steam did not answer within %d s' % timeout)
            time.sleep(0.25)
        # the result struct's size differs between SDK versions; a mismatch leaves the result in place
        for size in sizes:
            buf = ctypes.create_string_buffer(size)
            if self.api.SteamAPI_ISteamUtils_GetAPICallResult(self.utils, call, buf, size, callback, byref(failed)) and not failed.value:
                return buf.raw
        sys.exit('Steam call failed (ESteamAPICallFailure %d)' % self.api.SteamAPI_ISteamUtils_GetAPICallFailureReason(self.utils, call))

    def update(self, fileid, title=None, description=None, preview=None, content=None, visibility=None, tags=None, note=''):
        api, ugc = self.api, self.ugc
        h = api.SteamAPI_ISteamUGC_StartItemUpdate(ugc, APP, fileid)
        steps = [(title, api.SteamAPI_ISteamUGC_SetItemTitle), (description, api.SteamAPI_ISteamUGC_SetItemDescription),
                 (preview, api.SteamAPI_ISteamUGC_SetItemPreview), (content, api.SteamAPI_ISteamUGC_SetItemContent)]
        for value, fn in steps:
            if value is not None and not fn(ugc, h, value.encode('utf-8')):
                sys.exit('%s refused %r' % (fn.__name__, value[:60]))
        if visibility is not None and not api.SteamAPI_ISteamUGC_SetItemVisibility(ugc, h, visibility):
            sys.exit('SetItemVisibility refused %d' % visibility)
        if tags is not None:
            arr = (c_char_p * len(tags))(*[t.encode('utf-8') for t in tags])
            if not api.SteamAPI_ISteamUGC_SetItemTags(ugc, h, byref(Strings(arr, len(tags)))):
                sys.exit('SetItemTags refused %s' % tags)
        call = api.SteamAPI_ISteamUGC_SubmitItemUpdate(ugc, h, note.encode('utf-8'))
        raw = self.wait(call, CB_SUBMIT, (16, 8), handle=h)
        return int.from_bytes(raw[0:4], 'little'), raw[4] != 0          # EResult, needs the legal agreement

    def create(self, filetype=0):
        """filetype: Steam's EWorkshopFileType, 0 community item, 2 collection."""
        raw = self.wait(self.api.SteamAPI_ISteamUGC_CreateItem(self.ugc, APP, filetype), CB_CREATE, (24,))
        return int.from_bytes(raw[0:4], 'little'), int.from_bytes(raw[8:16], 'little'), raw[16] != 0

    def require(self, parent, child):
        raw = self.wait(self.api.SteamAPI_ISteamUGC_AddDependency(self.ugc, parent, child), CB_DEPENDENCY, (24,))
        return int.from_bytes(raw[0:4], 'little')


def result(code):
    return '%d %s' % (code, ERESULT.get(code, ''))


def linked(code):
    """AddDependency's answer: DuplicateRequest means the link was already there."""
    return 'already there' if code == 29 else 'added' if code == 1 else result(code)


LEGAL = 'accept the Workshop legal agreement first: https://steamcommunity.com/sharedfiles/workshoplegalagreement'


# --------------------------------------------------------------- actions --

def check(steam, packer, its, fields):
    owner = getattr(packer, 'OWNER', None)
    print('Steam: signed in as %d%s' % (steam.steamid, '' if owner is None else
                                       ' (the items\' owner)' if steam.steamid == owner else ' - NOT the owner %d' % owner))
    print('       interfaces: ' + ', '.join('%s via %s' % kv for kv in steam.route.items()))
    pages = live([i['id'] for i in its])
    for i in its:
        page = pages.get(i['id'])
        state = ('%s, updated %s' % (VISIBILITY_NAME.get(page.get('visibility'), '?'), time.strftime('%Y-%m-%d %H:%M', time.localtime(page['time_updated'])))
                 if page else 'not public or not on Steam')
        print('%-18s %-10d %s' % (i['key'], i['id'], state))
        if page:
            if page.get('title') != i['title']:
                print('    title differs: live %r' % page.get('title'))
            if page.get('description', '').replace('\r\n', '\n').strip() != i['description'].replace('\r\n', '\n').strip():
                print('    description differs from the packer')
            if STEAM_VISIBILITY.get(i['visibility']) != page.get('visibility'):
                print('    visibility: live %s, the packer says %s' % (VISIBILITY_NAME.get(page.get('visibility')),
                                                                      VISIBILITY_NAME.get(STEAM_VISIBILITY.get(i['visibility']))))
        for p in problems(i, fields):
            print('    cannot upload %s: %s' % ('/'.join(fields) or 'it', p))


def upload(steam, its, fields, note):
    before = live([i['id'] for i in its])
    for i in its:
        print('%s (%d): %s' % (i['key'], i['id'], ', '.join(fields)), flush=True)
        code, legal = steam.update(
            i['id'],
            title=i['title'] if 'title' in fields else None,
            description=i['description'] if 'description' in fields else None,
            preview=os.path.join(folder(i), 'previewimage.png') if 'preview' in fields else None,
            content=folder(i) if 'content' in fields else None,
            visibility=STEAM_VISIBILITY[i['visibility']] if 'visibility' in fields else None,
            note=note)
        print('    %s%s' % (result(code), ' - ' + LEGAL if legal else ''))
        if code != 1:
            sys.exit('stopped at %s' % i['key'])
    time.sleep(3)
    after = live([i['id'] for i in its])
    for i in its:
        b, a = before.get(i['id']), after.get(i['id'])
        if a and b:
            print('%-18s %s' % (i['key'], 'updated on Steam' if a['time_updated'] > b['time_updated'] else 'Steam still shows the old time - check the page'))


def create(steam, its):
    for i in its:
        if on_steam(i):
            print('%s already exists: %d' % (i['key'], i['id']))
            continue
        code, fileid, legal = steam.create()
        if code != 1:
            sys.exit('%s: CreateItem %s%s' % (i['key'], result(code), ' - ' + LEGAL if legal else ''))
        png = os.path.join(folder(i), 'previewimage.png')
        code, legal = steam.update(fileid, title=i['title'], description=i['description'], visibility=2,
                                   preview=png if os.path.exists(png) else None, tags=[TYPE_TAG[i['type']]],
                                   note='Created with tools/workshop_upload.py')
        print('%s: created %d (private) - %s%s' % (i['key'], fileid, result(code), ' - ' + LEGAL if legal else ''))
    print('Put the new ids in the packer\'s ITEMS, regenerate, run build.ps1 -Install, then upload "content visibility".')


def collection(steam, packer, note):
    """Creates the packer's collection if it has no id yet, sets its page, then adds its items in order
    (for a collection, AddDependency adds the item to it; items already in it stay)."""
    c = packer.workshop_collection()
    if len(c['description']) >= 8000 or not os.path.exists(c['preview']) or os.path.getsize(c['preview']) >= 1 << 20:
        sys.exit('collection: the description must stay under 8000 characters and %s exist under 1 MB '
                 '(python tools/space_thumbs.py compose collection)' % c['preview'])
    cid = c['id']
    if not cid:
        code, cid, legal = steam.create(2)
        if code != 1:
            sys.exit('CreateItem (collection) %s%s' % (result(code), ' - ' + LEGAL if legal else ''))
        print('collection created: %d - put COLLECTION_ID = %d in %s.py' % (cid, cid, packer.__name__))
    code, legal = steam.update(cid, title=c['title'], description=c['description'], preview=c['preview'],
                               visibility=STEAM_VISIBILITY[c['visibility']], note=note)
    print('collection %d page: %s%s' % (cid, result(code), ' - ' + LEGAL if legal else ''))
    for child in c['items']:
        print('    + %d: %s' % (child, linked(steam.require(cid, child))))
    print('https://steamcommunity.com/sharedfiles/filedetails/?id=%d' % cid)


def required(steam, its):
    for i in its:
        for child in i['required']:
            if not on_steam(i) or child < 100000000:
                print('%s -> %s: not on Steam yet, skipped' % (i['key'], child))
                continue
            print('%s (%d) requires %d: %s' % (i['key'], i['id'], child, linked(steam.require(i['id'], child))))


def main():
    ap = argparse.ArgumentParser(description='Steam Workshop items of the mods, without the game.')
    ap.add_argument('mod', choices=sorted(MODS))
    ap.add_argument('what', nargs='*', help='fields (%s, all) or one action (%s)' % (', '.join(FIELDS), ', '.join(ACTIONS)))
    ap.add_argument('--only', help='comma-separated item keys')
    ap.add_argument('--note', default='', help='change note shown on the item\'s Change Notes tab')
    ap.add_argument('--check', action='store_true', help='report only; nothing is sent to Steam')
    a = ap.parse_args()
    what = list(FIELDS) if 'all' in a.what else a.what
    actions = [w for w in what if w in ACTIONS]
    fields = [w for w in what if w in FIELDS]
    bad = [w for w in what if w not in FIELDS + ACTIONS]
    if bad or (actions and (fields or len(actions) > 1)) or not (what or a.check):
        ap.error('give fields to upload, or one action, or --check')
    packer, its = items(a.mod, a.only)
    if 'content' in fields and not a.check:
        running = game_running()
        if running:
            sys.exit('close %s first: the plugins write into their item folder and keep files open' % ', '.join(running))
    if fields and not a.check:
        blocking = {i['key']: problems(i, fields) for i in its}
        blocking = {k: v for k, v in blocking.items() if v}
        if blocking:
            sys.exit('\n'.join('%s: %s' % (k, '; '.join(v)) for k, v in blocking.items()))
    steam = Steam()
    try:
        if a.check:
            check(steam, packer, its, fields)
        elif actions == ['create']:
            create(steam, its)
        elif actions == ['required']:
            required(steam, its)
        elif actions == ['collection']:
            collection(steam, packer, a.note or 'Updated with tools/workshop_upload.py')
        else:
            upload(steam, its, fields, a.note or 'Updated: ' + ', '.join(fields))
    finally:
        steam.close()


if __name__ == '__main__':
    main()
