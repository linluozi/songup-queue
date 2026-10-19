"""Package the delivery ZIP and prove the archive round-trips byte for byte.

    python tools/make_zip.py

Produces ``songstub-2.1.0.zip`` in the project root, then:
  1. re-opens the archive and compares every entry's SHA-256 against the file
     on disk (catches truncation, encoding damage, duplicate entries);
  2. checks the archive contains no VCS metadata, no virtualenv, no __pycache__;
  3. checks LICENSE is present and byte-identical to the working copy;
  4. extracts to a temp dir and runs the unit suite there, so the ZIP is proven
     to be runnable rather than merely present.

Windows note: files are written with ``shutil.copyfile`` semantics via ZipFile
directly (not ``copy2``), because copy2 preserves the read-only bit and then a
re-run fails with WinError 32.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = "songstub-2.1.0.zip"
OUT = os.path.join(ROOT, NAME)

#: Everything that ships. Directories are walked; a short allow-list is used
#: instead of a deny-list so a stray virtualenv can never leak into a release.
INCLUDE_DIRS = ["templates", "static", "tests", "verify", "tools", "docs"]
INCLUDE_FILES = [
    "app.py", "queue_engine.py", "qrmini.py",
    "requirements.txt", "start.cmd",
    "README.md", "LICENSE", "NOTICE.md", "CHANGELOG.md",
    ".gitignore", ".gitattributes",
]
EXCLUDE_DIR_NAMES = {"__pycache__", ".venv", ".git", "outputs", ".pytest_cache", ".idea", ".vscode"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect():
    """Yield (absolute path, archive name) for everything that should ship."""
    for name in INCLUDE_FILES:
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            yield path, name
        else:
            print("  ! missing, skipped: %s" % name)

    for top in INCLUDE_DIRS:
        base = os.path.join(ROOT, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIR_NAMES)
            for filename in sorted(filenames):
                if filename.endswith(EXCLUDE_SUFFIXES):
                    continue
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                yield path, rel


def build(entries):
    if os.path.exists(OUT):
        os.remove(OUT)          # no copy2: avoid the read-only attribute trap
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, rel in entries:
            zf.write(path, rel)
    return OUT


def verify(entries):
    problems = []

    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            problems.append("duplicate entries in archive")
        for path, rel in entries:
            if rel not in names:
                problems.append("missing from archive: %s" % rel)
                continue
            with zf.open(rel) as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if digest != sha256(path):
                problems.append("byte mismatch: %s" % rel)

        for name in names:
            if name.startswith((".git/", ".venv/")) or "/__pycache__/" in name:
                problems.append("forbidden path in archive: %s" % name)
            if name.endswith((".pyc", ".pyo", ".log")):
                problems.append("forbidden suffix in archive: %s" % name)

        if "LICENSE" not in names:
            problems.append("LICENSE missing")
        else:
            with zf.open("LICENSE") as fh:
                if fh.read() != open(os.path.join(ROOT, "LICENSE"), "rb").read():
                    problems.append("LICENSE differs from working copy")

    # Run the suite from the extracted archive: "it unzips" is not "it works".
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(OUT) as zf:
            zf.extractall(tmp)
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=tmp, capture_output=True, text=True,
        )
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:]
        if proc.returncode != 0:
            problems.append("tests fail in extracted copy: %s" % (tail[0] if tail else "?"))
        else:
            print("  extracted copy: %s" % (tail[0] if tail else "ok"))

        # The app itself must import from the extracted copy.
        imp = subprocess.run(
            [sys.executable, "-c", "import app, qrmini, queue_engine; print('imports ok')"],
            cwd=tmp, capture_output=True, text=True,
        )
        if imp.returncode != 0:
            problems.append("imports fail in extracted copy: %s" % imp.stderr.strip().splitlines()[-1:])
        else:
            print("  extracted copy: imports ok")

    return problems


def main():
    entries = list(collect())
    build(entries)
    size = os.path.getsize(OUT)
    digest = sha256(OUT)
    print("%s  %d files  %d bytes" % (NAME, len(entries), size))
    print("sha256 %s" % digest)

    problems = verify(entries)
    if problems:
        print("\nFAILED:")
        for p in problems:
            print("  - " + p)
        return 1
    print("\nOK: %d/%d entries byte-identical, tests green in extracted copy" % (len(entries), len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
