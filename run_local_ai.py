#!/usr/bin/env python3
"""Run Royalty Loom and a real local llama.cpp model without API credentials.

Linux x86-64 can prepare the pinned runtime with --download. Other platforms
can pass their installed llama-server executable and a GGUF model file.
"""
from __future__ import annotations
from dataclasses import dataclass
import tempfile
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
MODEL_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_REVISION = "91cad51170dc346986eccefdc2dd33a9da36ead9"
MODEL_SHA = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
RUNTIME_TAG = "b12250"
RUNTIME_SHA = "5a2cb0188a3f392f88c5d226768abd0da7b2b6a5abdbb50abedcd7c8f42d9fb1"
RUNTIME_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{RUNTIME_TAG}/llama-{RUNTIME_TAG}-bin-ubuntu-x64.tar.gz"
MODEL_URL = f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{MODEL_REVISION}/{MODEL_NAME}"


class LocalAICancelled(RuntimeError):
    """An explicit stop interrupted setup or startup."""

def check_cancelled(cancelled=None):
    if cancelled and cancelled():
        raise LocalAICancelled("Local AI setup was cancelled.")

def report(progress, phase, asset="", completed_bytes=None, total_bytes=None):
    if progress:
        progress({"phase": phase, "asset": asset,
                  "completed_bytes": completed_bytes, "total_bytes": total_bytes})

def default_cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache")))/"royalty-loom"/"local-ai"

def digest(path: Path, *, progress=None, cancelled=None, asset=None) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size
    completed = 0
    report(progress, "verifying", asset or path.name, completed, total)
    with path.open("rb") as source:
        while True:
            check_cancelled(cancelled)
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            completed += len(chunk)
            report(progress, "verifying", asset or path.name, completed, total)
    return h.hexdigest()

def download(url: str, path: Path, expected: str, *, progress=None, cancelled=None):
    check_cancelled(cancelled)
    if path.exists() and digest(path, progress=progress, cancelled=cancelled) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+".", suffix=".download", delete=False) as pending:
        partial = Path(pending.name)
    print(f"Downloading {path.name} …", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=10) as response, partial.open("wb") as target:
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            completed = 0
            report(progress, "download", path.name, 0, total)
            while True:
                check_cancelled(cancelled)
                chunk = response.read(64 * 1024)
                check_cancelled(cancelled)
                if not chunk:
                    break
                target.write(chunk)
                completed += len(chunk)
                report(progress, "download", path.name, completed, total)
        if digest(partial, progress=progress, cancelled=cancelled, asset=path.name) != expected:
            raise RuntimeError(f"Checksum failed for {path.name}; no downloaded program was launched.")
        check_cancelled(cancelled)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)

def prepare_runtime(cache: Path, *, progress=None, cancelled=None) -> Path:
    if platform.system() != "Linux" or platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("--download is currently tested for Linux x86-64 only. "
                           "Install llama.cpp for your platform, then pass --server and --model-file.")
    check_cancelled(cancelled)
    archive = cache / f"llama-{RUNTIME_TAG}.tar.gz"
    download(RUNTIME_URL, archive, RUNTIME_SHA, progress=progress, cancelled=cancelled)
    destination = cache / f"runtime-{RUNTIME_TAG}-{RUNTIME_SHA[:12]}"
    binary = destination / f"llama-{RUNTIME_TAG}" / "llama-server"
    marker = destination / "VERIFIED_ARCHIVE_SHA256"
    ready = binary.is_file() and marker.is_file() and marker.read_text().strip() == RUNTIME_SHA
    destination.mkdir(parents=True, exist_ok=True)
    if not ready:
        marker.unlink(missing_ok=True)
        # The archive is content-pinned; still reject any member escaping its cache.
        with tarfile.open(archive) as package:
            members = package.getmembers()
            for member in members:
                check_cancelled(cancelled)
                resolved = (destination / member.name).resolve()
                if not resolved.is_relative_to(destination.resolve()):
                    raise RuntimeError("Runtime archive member escapes the local model cache.")
                if member.issym():
                    target = (resolved.parent / member.linkname).resolve()
                    if not target.is_relative_to(destination.resolve()):
                        raise RuntimeError("Runtime archive link escapes the local model cache.")
                elif member.islnk():
                    target = (destination / member.linkname).resolve()
                    if not target.is_relative_to(destination.resolve()):
                        raise RuntimeError("Runtime archive link escapes the local model cache.")
            for member in members:
                check_cancelled(cancelled)
                report(progress, "extracting", member.name)
                if sys.version_info >= (3, 12):
                    package.extract(member, destination, filter="data")
                else:
                    package.extract(member, destination)
        marker.write_text(RUNTIME_SHA + "\n")
    check_cancelled(cancelled)
    return binary

def prepare(cache: Path, *, progress=None, cancelled=None) -> tuple[Path, Path]:
    binary = prepare_runtime(cache, progress=progress, cancelled=cancelled)
    model = cache / MODEL_NAME
    download(MODEL_URL, model, MODEL_SHA, progress=progress, cancelled=cancelled)
    check_cancelled(cancelled)
    return binary, model

def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]

def stop(process: subprocess.Popen | None):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@dataclass
class LocalModel:
    process: subprocess.Popen
    url: str
    log_path: Path
    model: str = "royalty-local"

def start_model(server: Path, model: Path, cache: Path, *, threads=None,
                progress=None, cancelled=None) -> LocalModel:
    check_cancelled(cancelled)
    threads = threads if threads is not None else max(1, min(3, (os.cpu_count() or 2)-1))
    if threads < 1:
        raise ValueError("Use at least one CPU thread.")
    model_port = available_port()
    cache.mkdir(parents=True, exist_ok=True)
    log_path = cache / f"llama-{model_port}.log"
    process = None
    report(progress, "starting", model.name)
    try:
        with log_path.open("w") as model_log:
            process = subprocess.Popen(
                [str(server.resolve()), "-m", str(model.resolve()), "--host", "127.0.0.1",
                 "--port", str(model_port), "-c", "8192", "-t", str(threads),
                 "-np", "1", "--alias", "royalty-local"],
                stdout=model_log, stderr=model_log)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            check_cancelled(cancelled)
            if process.poll() is not None:
                raise RuntimeError(f"Local model stopped during startup. Details: {log_path}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{model_port}/health", timeout=1) as response:
                    if json.load(response).get("status") == "ok":
                        check_cancelled(cancelled)
                        handle = LocalModel(process, f"http://127.0.0.1:{model_port}/v1/chat/completions", log_path)
                        report(progress, "ready", model.name)
                        return handle
            except (OSError, ValueError):
                pass
            time.sleep(.25)
        raise RuntimeError(f"Local model did not become ready within 60 seconds. Details: {log_path}")
    except BaseException:
        stop(process)
        raise

def stop_model(handle: LocalModel | None):
    if handle is not None:
        stop(handle.process)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download and verify the pinned Linux CPU runtime and 1.12 GB model.")
    parser.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    parser.add_argument("--server", type=Path, help="Installed llama-server executable.")
    parser.add_argument("--model-file", type=Path, help="Local GGUF model file.")
    parser.add_argument("--port", type=int, default=8733, help="Royalty Loom browser port.")
    parser.add_argument("--threads", type=int, default=max(1, min(3, (os.cpu_count() or 2)-1)))
    parser.add_argument("--prepare-only", action="store_true", help="Prepare the runtime and model, then exit without serving.")
    options = parser.parse_args()
    if options.download:
        server, model = prepare(options.cache_dir)
    else:
        installed = shutil.which("llama-server")
        server = options.server or (Path(installed) if installed else None)
        model = options.model_file
    if not server or not server.is_file() or not model or not model.is_file():
        parser.error("Provide --server and --model-file, or use --download on Linux x86-64.")
    if not 1 <= options.port <= 65535 or options.threads < 1:
        parser.error("Use a valid browser port and at least one CPU thread.")
    print(f"Local model: {model.name}; no remote AI API or API key is used.", flush=True)
    if options.prepare_only:
        return 0

    handle = app_process = None
    try:
        handle = start_model(server, model, options.cache_dir, threads=options.threads)
        environment = {**os.environ, "PORT": str(options.port),
                       "ROYALTY_LOOM_AI_URL": handle.url,
                       "ROYALTY_LOOM_AI_MODEL": handle.model}
        environment.pop("ROYALTY_LOOM_AI_KEY", None)
        print(f"Open http://127.0.0.1:{options.port}. Press Ctrl+C to stop both local processes.", flush=True)
        app_command = [str(ROOT / "royalty-loom")] if FROZEN else [sys.executable, str(ROOT / "app.py")]
        app_process = subprocess.Popen(app_command, cwd=ROOT, env=environment)
        return app_process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        stop(app_process)
        stop_model(handle)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as error:
        print(f"Local AI could not start: {error}", file=sys.stderr)
        raise SystemExit(1)
