"""
User playlists for the desktop — a port of the mobile app's Playlists.kt.
Persisted to playlists.json (config_dir). Each playlist = {id, name, paths[]}.
Callers hold the live list (from load()) and mutate it through these helpers,
which save to disk on every change.
"""

import json
import time

import licensing


def _file():
    return licensing.config_dir() / "playlists.json"


def load():
    f = _file()
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        raw = data if isinstance(data, list) else (data.get("playlists") or [])
        out = []
        for p in raw:
            if isinstance(p, dict):
                out.append({
                    "id": str(p.get("id") or int(time.time() * 1000)),
                    "name": p.get("name") or "Playlist",
                    "paths": [x for x in (p.get("paths") or []) if x],
                })
        return out
    except Exception:  # noqa: BLE001
        return []


def save(items):
    try:
        _file().write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def create(items, name):
    p = {"id": str(int(time.time() * 1000)),
         "name": (name or "Playlist").strip() or "Playlist", "paths": []}
    items.insert(0, p)
    save(items)
    return p


def add_paths(items, pid, paths):
    n = 0
    for p in items:
        if p["id"] == pid:
            for path in paths:
                if path and path not in p["paths"]:
                    p["paths"].append(path)
                    n += 1
            save(items)
            break
    return n


def remove_path(items, pid, path):
    for p in items:
        if p["id"] == pid:
            p["paths"] = [x for x in p["paths"] if x != path]
            save(items)
            break


def delete(items, pid):
    items[:] = [p for p in items if p["id"] != pid]
    save(items)


def rename(items, pid, name):
    for p in items:
        if p["id"] == pid:
            p["name"] = (name or p["name"]).strip() or p["name"]
            save(items)
            break
