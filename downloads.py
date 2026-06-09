"""
Background download queue for Universal Media Downloader.
=========================================================
Lets every mode (Single, Bulk, Channel/Profile) keep working at once. Instead
of blocking the Streamlit script while a download runs, jobs are handed to a
small pool of background worker threads; the UI just enqueues and then watches
live progress. So you can fire a quick single download while a 990-video channel
grab keeps chugging in the background.

Two lanes keep things responsive:
  * "now"   — Single / Bulk: interactive jobs, run on dedicated workers so they
              start immediately and never wait behind a big channel grab.
  * "batch" — Channel / Profile "download all": throughput-limited so it can't
              hog every worker.

Pure logic, NO Streamlit — importable/testable and works the same when frozen.
"""

import queue
import threading
import uuid
from datetime import datetime

import downloader as dl
import history as hist
from downloader import Canceled  # re-exported; raised to abort an in-flight job

LANE_NOW = "now"
LANE_BATCH = "batch"


class Job:
    __slots__ = ("id", "url", "fmt", "quality", "audio_codec", "dest_dir",
                 "title", "opts", "lane", "status", "progress", "detail",
                 "result", "error", "added", "started", "finished", "cancel")

    def __init__(self, url, fmt, quality, audio_codec, dest_dir, title, opts, lane):
        self.id = uuid.uuid4().hex[:8]
        self.url = url
        self.fmt = fmt
        self.quality = quality
        self.audio_codec = audio_codec or "mp3"
        self.dest_dir = dest_dir
        self.title = title or ""
        self.opts = opts or {}
        self.lane = lane
        self.status = "queued"      # queued | downloading | done | error | canceled
        self.progress = 0.0
        self.detail = "Queued"
        self.result = None
        self.error = None
        self.added = datetime.now()
        self.started = None
        self.finished = None
        self.cancel = False

    @property
    def label(self):
        return self.title or self.url


class DownloadManager:
    def __init__(self, now_workers=2, batch_workers=2):
        self._q = {LANE_NOW: queue.Queue(), LANE_BATCH: queue.Queue()}
        self._jobs = {}
        self._order = []
        self._lock = threading.Lock()
        self._started = False
        self._now_workers = now_workers
        self._batch_workers = batch_workers

    # -- lifecycle -------------------------------------------------------- #
    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
        for _ in range(self._now_workers):
            threading.Thread(target=self._work, args=(LANE_NOW,), daemon=True).start()
        for _ in range(self._batch_workers):
            threading.Thread(target=self._work, args=(LANE_BATCH,), daemon=True).start()

    # -- enqueue ---------------------------------------------------------- #
    def add(self, job):
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        self._q[job.lane].put(job.id)
        return job.id

    def add_jobs(self, specs, lane):
        """specs: list of dicts with url, fmt, quality, audio_codec, dest_dir,
        title, opts. Returns the list of new job ids."""
        ids = []
        for s in specs:
            j = Job(s["url"], s["fmt"], s.get("quality"),
                    s.get("audio_codec", "mp3"), s["dest_dir"],
                    s.get("title", ""), s.get("opts", {}), lane)
            ids.append(self.add(j))
        return ids

    # -- inspect ---------------------------------------------------------- #
    def snapshot(self):
        with self._lock:
            return [self._jobs[i] for i in self._order]

    def get(self, jid):
        with self._lock:
            return self._jobs.get(jid)

    def counts(self):
        s = self.snapshot()
        return {
            "queued": sum(j.status == "queued" for j in s),
            "active": sum(j.status == "downloading" for j in s),
            "done": sum(j.status == "done" for j in s),
            "error": sum(j.status == "error" for j in s),
            "canceled": sum(j.status == "canceled" for j in s),
            "total": len(s),
        }

    # -- control ---------------------------------------------------------- #
    def cancel(self, jid):
        with self._lock:
            j = self._jobs.get(jid)
            if j:
                j.cancel = True
                if j.status == "queued":
                    j.status = "canceled"
                    j.detail = "Canceled"

    def cancel_all(self):
        with self._lock:
            for j in self._jobs.values():
                if j.status in ("queued", "downloading"):
                    j.cancel = True
                    if j.status == "queued":
                        j.status = "canceled"
                        j.detail = "Canceled"

    def clear_finished(self):
        with self._lock:
            keep = [i for i in self._order
                    if self._jobs[i].status in ("queued", "downloading")]
            self._order = keep
            self._jobs = {i: self._jobs[i] for i in keep}

    # -- worker ----------------------------------------------------------- #
    def _work(self, lane):
        q = self._q[lane]
        while True:
            jid = q.get()
            try:
                j = self.get(jid)
                if not j or j.cancel or j.status == "canceled":
                    if j and j.status != "canceled":
                        j.status = "canceled"
                        j.detail = "Canceled"
                    continue
                self._run(j)
            except Exception:  # noqa: BLE001 — a worker must never die
                pass
            finally:
                q.task_done()

    def _run(self, j):
        j.status = "downloading"
        j.started = datetime.now()
        j.detail = "Starting…"
        j.progress = 0.0
        cookiefile = j.opts.get("cookiefile", "")
        extractor = ""

        def prog(f):
            if j.cancel:
                raise Canceled()
            try:
                j.progress = max(0.0, min(1.0, float(f)))
            except (TypeError, ValueError):
                pass

        def stat(t):
            if j.cancel:
                raise Canceled()
            j.detail = t

        try:
            # If we don't have a real title yet (e.g. a pasted bulk link), fetch
            # it in the background so the saved file is named nicely.
            if not j.title or j.title == j.url:
                stat("Reading details…")
                try:
                    m = dl.extract_meta(j.url, cookiefile)
                    j.title = m.get("title") or j.url
                    extractor = m.get("extractor", "")
                except Exception:  # noqa: BLE001
                    pass
            path = dl.download_with_retry(
                j.url, j.fmt, j.quality, j.audio_codec, j.dest_dir,
                j.title or j.url, j.opts.get("use_aria2c", False), cookiefile,
                j.opts.get("embed_meta", True), j.opts.get("trim"),
                progress_cb=prog, status_cb=stat)
            j.result = path
            j.status = "done"
            j.progress = 1.0
            j.detail = "Saved"
            try:
                hist.add_entry(path, j.title or path, j.fmt, url=j.url,
                               extractor=extractor)
            except Exception:  # noqa: BLE001
                pass
        except Canceled:
            j.status = "canceled"
            j.detail = "Canceled"
        except Exception as e:  # noqa: BLE001
            j.status = "error"
            j.error = str(e)
            j.detail = "Failed"
        finally:
            j.finished = datetime.now()


_manager = None
_mlock = threading.Lock()


def get_manager():
    """One shared manager per app process (persists across Streamlit reruns)."""
    global _manager
    with _mlock:
        if _manager is None:
            _manager = DownloadManager()
            _manager.start()
        return _manager
