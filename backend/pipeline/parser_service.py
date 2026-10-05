"""Two bounded parser subprocesses, fed only through a private spool; no network namespace."""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def run(directory):
    try:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("source_parser.py")), str(directory)],
            cwd=directory,
            env={"PATH": os.defpath, "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 305
            while process.poll() is None:
                if not directory.exists() or time.monotonic() >= deadline:
                    raise subprocess.SubprocessError("Parser cancelled or timed out")
                time.sleep(0.25)
            if process.returncode != 0:
                raise subprocess.SubprocessError("Parser failed")
        finally:
            # This group belongs only to this job, including any Tesseract child.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if (directory / "result.json").exists():
            return
    except (subprocess.SubprocessError, OSError):
        pass
    if directory.exists():
        (directory / "result.tmp").write_text(
            json.dumps({"error": "Extraction exceeded its time or memory limit."})
        )
        (directory / "result.tmp").replace(directory / "result.json")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    # A container restart kills its children; reclaim only unfinished parser requests.
    for working in ROOT.glob("*/working"):
        if not (working.parent / "result.json").exists():
            working.rename(working.with_name("request"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        active = []
        while True:
            active = [future for future in active if not future.done()]
            for request in ROOT.glob("*/request"):
                if len(active) >= 2:
                    break
                directory = request.parent.resolve()
                try:
                    uuid.UUID(directory.name)
                    if directory.parent != ROOT or directory.is_symlink():
                        continue
                    request.rename(directory / "working")
                except (ValueError, OSError):
                    continue
                active.append(pool.submit(run, directory))
            time.sleep(0.25)


if __name__ == "__main__":
    main()
