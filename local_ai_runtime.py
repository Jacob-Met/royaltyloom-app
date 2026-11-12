"""Explicit, process-owned local AI lifecycle for the existing web app."""
from __future__ import annotations
import os
from pathlib import Path
import platform
import threading
import run_local_ai as launcher

class LocalAIRuntime:
    def __init__(self, cache=None, *, backend=launcher):
        self.cache = Path(cache) if cache is not None else launcher.default_cache_dir()
        self.backend = backend
        self._lock = threading.RLock()
        self._thread = None
        self._cancel = threading.Event()
        self._handle = None
        self._stop_in_progress = False
        self._stop_complete = threading.Event()
        self._stop_complete.set()
        self._state = "idle"
        self._message = "Local AI has not been started."
        self._progress = None

    @staticmethod
    def _external():
        return bool(os.environ.get("ROYALTY_LOOM_AI_URL", "").strip() or os.environ.get("ROYALTY_LOOM_AI_MODEL", "").strip())

    @staticmethod
    def _external_ready():
        return bool(os.environ.get("ROYALTY_LOOM_AI_URL", "").strip() and os.environ.get("ROYALTY_LOOM_AI_MODEL", "").strip())

    def _refresh_locked(self):
        if not self._stop_in_progress and self._handle is not None and self._handle.process.poll() is not None:
            self._handle = None
            self._state = "error"
            self._message = "The local model stopped. Start local AI again to retry."
            self._progress = None

    def snapshot(self):
        with self._lock:
            self._refresh_locked()
            supported = platform.system() == "Linux" and platform.machine().lower() in ("x86_64", "amd64")
            external = self._external()
            local_ready = self._state == "ready" and self._handle is not None
            adapter = "external" if self._external_ready() else ("local" if local_ready and not external else "none")
            reason = ("An external AI configuration is already supplied; it will not be replaced." if external else "" if supported else "Automatic local setup supports Linux x86-64 only.")
            return {"state": self._state, "available": supported and not external, "reason": reason,
                    "message": self._message, "progress": dict(self._progress) if self._progress else None,
                    "configured": adapter != "none", "adapter": adapter, "owned_process": self._handle is not None}

    def adapter(self):
        with self._lock:
            self._refresh_locked()
            if not self._external() and self._state == "ready" and self._handle is not None:
                return self._handle.url, self._handle.model
            return None

    def start(self, acknowledgement):
        if acknowledgement is not True:
            raise ValueError("Explicit acknowledgement of the approximately 1.14 GB initial download is required.")
        with self._lock:
            info = self.snapshot()
            if not info["available"]:
                raise ValueError(info["reason"])
            if self._stop_in_progress or self._handle is not None or self._thread is not None:
                return info
            self._cancel = threading.Event()
            cancel = self._cancel
            self._state, self._message = "preparing", "Preparing the verified local runtime and model."
            self._progress = None
            self._thread = threading.Thread(target=self._run, args=(cancel,), daemon=True, name="royalty-local-ai")
            self._thread.start()
            return self.snapshot()

    def _report(self, cancel, event):
        with self._lock:
            if cancel is not self._cancel or cancel.is_set():
                return
            phase = event.get("phase")
            messages = {"download": "Downloading pinned local AI files.", "verifying": "Verifying the downloaded files.",
                        "extracting": "Preparing the verified local runtime.", "starting": "Starting the local model.",
                        "ready": "The local model is ready."}
            if phase not in messages:
                return
            self._state = "starting" if phase in ("starting", "ready") else "preparing"
            self._message = messages[phase]
            self._progress = {"phase": phase, "asset": str(event.get("asset") or "")[:120],
                              "completed_bytes": event.get("completed_bytes"), "total_bytes": event.get("total_bytes")}

    def _run(self, cancel):
        unowned_handle = None
        try:
            callback = lambda event: self._report(cancel, event)
            server, model = self.backend.prepare(self.cache, progress=callback, cancelled=cancel.is_set)
            if cancel.is_set():
                return
            unowned_handle = self.backend.start_model(server, model, self.cache, progress=callback, cancelled=cancel.is_set)
            with self._lock:
                if not cancel.is_set():
                    self._handle, unowned_handle = unowned_handle, None
                    self._state, self._message = "ready", "Local AI is ready. Agreement text stays on this computer."
        except Exception as error:
            with self._lock:
                if not cancel.is_set():
                    self._state, self._message = "error", "Local AI could not start: " + str(error)[:300]
                    self._progress = None
        finally:
            try:
                if unowned_handle is not None:
                    self.backend.stop_model(unowned_handle)
            finally:
                with self._lock:
                    self._thread = None
                    if cancel.is_set() and self._handle is None:
                        self._state = "idle"
                        self._message = "Local AI stopped. Verified downloaded files remain available for next time."
                        self._progress = None

    def stop(self, *, wait=False):
        with self._lock:
            pending_stop = self._stop_in_progress
            if not pending_stop:
                self._cancel.set()
                handle = self._handle
                thread = self._thread
                self._stop_in_progress = handle is not None
                if handle is not None:
                    self._stop_complete.clear()
                self._state = "stopping" if handle is not None or thread is not None else "idle"
                self._message = "Stopping local AI." if self._state == "stopping" else "Local AI is stopped."
                self._progress = None
        if pending_stop:
            if wait:
                self._stop_complete.wait(timeout=12)
            return self.snapshot()
        if handle is not None:
            try:
                self.backend.stop_model(handle)
            except Exception as error:
                with self._lock:
                    self._stop_in_progress = False
                    self._stop_complete.set()
                    self._state = "error"
                    self._message = "Could not stop the owned local model; choose Stop again: " + str(error)[:200]
                    return self.snapshot()
            with self._lock:
                if self._handle is handle:
                    self._handle = None
        if wait and thread is not None and thread is not threading.current_thread():
            thread.join(timeout=12)
        with self._lock:
            self._stop_in_progress = False
            self._stop_complete.set()
            if self._thread is None:
                self._state = "idle"
                self._message = "Local AI stopped. Verified downloaded files remain available for next time."
            return self.snapshot()
