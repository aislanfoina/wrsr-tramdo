"""Temporary Republic Mod Loader (WRSR Ultimate Pack) config for a test: only our development
items (Space Race package, kit, rockets, Tram DO) and the Workshop items without plugins enabled.

    python tools/dev/rml_testcfg.py playlist     # game and RML closed; then launch
    python tools/dev/rml_testcfg.py restore      # afterwards: the config as it was

The config before the first `playlist` is kept in rml_backup/config.pack-original.json beside this
script (saved automatically if missing). A named playlist is authoritative when the launcher
starts - everything it does not list is off. The Default playlist is not (`write`, kept for the
record): a Workshop item and its plugin DLLs share one switch, so hybrid items turn back on.
"""
import json, os, shutil, sys

PACK = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\784150\3838038411"
CFG = os.path.join(PACK, "rml", "config.json")
CONTENT = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\784150"
WIP = r"C:\Program Files (x86)\Steam\steamapps\common\SovietRepublic\media_soviet\workshop_wip"
HERE = os.path.dirname(os.path.abspath(__file__))
ORIG = os.path.join(HERE, "rml_backup", "config.pack-original.json")

OURS_DEV = ["3814049784", "3814050253", "3814050457", "3814050971", "3814051385",
            "3814051864", "3814052488", "3814373926"]
OLD_SUBSCRIBED = ["3814373926"]          # published 1.1.1.9 Tram DO
PLUGINS_ON = ["space-race.spacerace", "space-race.experts", "space-race.resources", "tram-do.tramdo"]
PLUGINS_OFF = [
    "tesmio.cablewaycustomshouse", "ultimate-universe.ultimate-pack", "tesmio.dockdistributionoffice",
    "tesmio.forcenodes.engine", "tesmio.forcenodes", "tesmio.free.heliports",
    "tesmio.helicopter.distribution.office", "tesmio.parallelutilities",
    "tesmio.rollingstockroadtransport", "tesmio.temporary.track",
    "ultimate-universe.factory-connections-enhanced", "tesmio.worker.workwear",
    "ultimate-universe.enhanced-storage-management", "tesmio.roadlampdirection",
    "tesmio.roadlampdirectionoverlay",
    "republic-in-ruins.fallout", "republic-in-ruins.scrap-center", "republic-in-ruins.survivors",
    "republic-in-ruins.trade-post", "republic-in-ruins.experts", "republic-in-ruins.spacerace",
    "republic-in-ruins.customs-market", "republic-in-ruins.customs-probe", "republic-in-ruins.customs-stock",
]


# Workshop items that carry plugin DLLs ("hybrid": item and plugin share one switch in RML)
HYBRID = ["3780813529", "3838038411", "3776862813", "3776818669", "3779842468", "3778940406", "3778344530",
          "3778366463", "3778730862", "3793100314", "3779416874", "3793101070", "3814373926"]


def playlist():
    """A named playlist is authoritative at launcher start: everything not listed is off.
    Development plugins follow their development item, not the plugin list."""
    if not os.path.exists(ORIG):
        os.makedirs(os.path.dirname(ORIG), exist_ok=True)
        shutil.copyfile(CFG, ORIG)
        print("saved the current config to", ORIG)
    with open(ORIG, encoding="utf-8") as f:
        cfg = json.load(f)
    ws = [d for d in sorted(os.listdir(CONTENT)) if d.isdigit() and d not in HYBRID]
    # every hybrid plugin id must exist in the map, or it defaults to enabled and switches its item back on
    cfg["plugins"] = {p: {"enabled": False, "force": False, "priority": 1000 + i}
                      for i, p in enumerate(PLUGINS_OFF + PLUGINS_ON)}
    cfg["playlists"] = [{"name": "srtest", "plugins": [], "workshop": ws, "development": OURS_DEV}]
    cfg["selectedPlaylist"] = "srtest"
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("playlist srtest:", len(ws), "workshop items,", len(OURS_DEV), "development items, no other plugins")


def write():
    with open(ORIG, encoding="utf-8") as f:
        cfg = json.load(f)
    plugins = {}
    for i, p in enumerate(PLUGINS_OFF):
        plugins[p] = {"enabled": False, "force": False, "priority": 1000 + i}
    for i, p in enumerate(PLUGINS_ON):
        plugins[p] = {"enabled": True, "force": False, "priority": 9760 + 10 * i}
    ws = {d: (d not in OLD_SUBSCRIBED) for d in sorted(os.listdir(CONTENT)) if d.isdigit()}
    dev = {d: (d in OURS_DEV) for d in sorted(os.listdir(WIP)) if d.isdigit()}
    cfg["plugins"] = plugins
    cfg["defaultPlugins"] = dict(plugins)
    cfg["workshopItems"] = ws
    cfg["defaultWorkshopItems"] = dict(ws)
    cfg["developmentItems"] = dev
    cfg["defaultDevelopmentItems"] = dict(dev)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("written:", CFG)
    print("workshop items:", sum(ws.values()), "on /", len(ws), "| dev items on:",
          [d for d, v in dev.items() if v], "| missing dev:", [d for d in OURS_DEV if d not in dev])


def restore():
    shutil.copyfile(ORIG, CFG)
    print("restored shipped config to", CFG)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("playlist", "restore", "write"):
        sys.exit(__doc__)
    {"write": write, "restore": restore, "playlist": playlist}[sys.argv[1]]()
