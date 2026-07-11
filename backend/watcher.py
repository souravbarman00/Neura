"""Per-chat workspace watcher — keeps a chat's local index fresh as files change.

For a watched conversation we run a watchdog Observer over its workspace folder.
File create/modify → re-index that one file into the chat's collection; delete →
drop its chunks. Events are debounced so a burst of saves re-indexes once.

Status is exposed for the UI top-bar indicator.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "coded_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "coded_tools"))

DEBOUNCE_SECONDS = 0.8


def _lib():
    from neura import ingest_lib  # noqa: WPS433

    return ingest_lib


class _Handler(FileSystemEventHandler):
    def __init__(self, mgr: "WatcherManager", cid: str):
        self._mgr = mgr
        self._cid = cid

    def on_any_event(self, event):
        if event.is_directory:
            return
        # rename/move report a dest_path
        for attr in ("src_path", "dest_path"):
            p = getattr(event, attr, None)
            if p:
                self._mgr._note(self._cid, p, deleted=(event.event_type == "deleted" and attr == "src_path"))


class WatcherManager:
    def __init__(self) -> None:
        self._w: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, cid: str, path: str, collection: str) -> Dict[str, Any]:
        self.stop(cid)
        root = Path(path)
        if not root.exists() or not root.is_dir():
            return {"watching": False, "error": f"workspace path not found: {path}"}
        observer = Observer()
        observer.schedule(_Handler(self, cid), str(root), recursive=True)
        observer.daemon = True
        observer.start()
        with self._lock:
            self._w[cid] = {
                "observer": observer,
                "path": str(root),
                "collection": collection,
                "pending": set(),
                "deleted": set(),
                "timer": None,
                "reindexing": False,
                "last_event": None,
                "reindex_count": 0,
                "started": time.time(),
                "error": None,
            }
        return self.status(cid)

    def stop(self, cid: str) -> None:
        with self._lock:
            w = self._w.pop(cid, None)
        if w:
            try:
                if w.get("timer"):
                    w["timer"].cancel()
                w["observer"].stop()
                w["observer"].join(timeout=2)
            except Exception:  # noqa: BLE001
                pass

    def status(self, cid: str) -> Dict[str, Any]:
        with self._lock:
            w = self._w.get(cid)
            if not w:
                return {"watching": False}
            return {
                "watching": True,
                "path": w["path"],
                "reindexing": w["reindexing"],
                "last_event": w["last_event"],
                "reindex_count": w["reindex_count"],
                "error": w["error"],
            }

    def _note(self, cid: str, path: str, deleted: bool) -> None:
        lib = _lib()
        if not deleted and not lib.is_indexable(path):
            return
        with self._lock:
            w = self._w.get(cid)
            if not w:
                return
            (w["deleted"] if deleted else w["pending"]).add(path)
            if w.get("timer"):
                w["timer"].cancel()
            t = threading.Timer(DEBOUNCE_SECONDS, self._flush, args=(cid,))
            t.daemon = True
            w["timer"] = t
            t.start()

    def _flush(self, cid: str) -> None:
        lib = _lib()
        with self._lock:
            w = self._w.get(cid)
            if not w:
                return
            pending = list(w["pending"])
            deleted = list(w["deleted"])
            w["pending"] = set()
            w["deleted"] = set()
            collection = w["collection"]
            w["reindexing"] = True
        try:
            last_name = None
            for p in deleted:
                lib.remove_file(p, collection=collection)
                last_name = Path(p).name
            for p in pending:
                if lib.is_indexable(p):
                    lib.index_file(p, collection=collection)
                    last_name = Path(p).name
            with self._lock:
                w = self._w.get(cid)
                if w:
                    w["reindexing"] = False
                    w["reindex_count"] += len(pending) + len(deleted)
                    if last_name:
                        w["last_event"] = {"name": last_name, "ts": time.time()}
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                w = self._w.get(cid)
                if w:
                    w["reindexing"] = False
                    w["error"] = str(exc)


manager = WatcherManager()
