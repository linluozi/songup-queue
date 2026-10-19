"""Check every image and link the README points at actually exists.

    python tools/check_readme.py

A broken image in a README is invisible to every test suite and visible to
everyone who opens the repo, so it gets its own check. Relative paths only;
external links are reported but not fetched.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
#: GitHub renders raw <img> tags too, and those are easy to leave dangling.
HTML_IMG = re.compile(r"<img\s[^>]*src=\"([^\"]+)\"")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def main():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        text = fh.read()

    missing = []
    local_images = 0
    for target in IMG.findall(text) + HTML_IMG.findall(text):
        target = target.split()[0].strip()
        if target.startswith(("http://", "https://", "data:")):
            continue
        local_images += 1
        path = os.path.join(ROOT, target)
        if not os.path.isfile(path):
            missing.append(("image", target))
        else:
            print("OK   image %-42s %8d bytes" % (target, os.path.getsize(path)))

    local_links = 0
    for target in LINK.findall(text):
        target = target.split()[0].strip()
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        local_links += 1
        path = os.path.join(ROOT, target.split("#")[0])
        if not os.path.exists(path):
            missing.append(("link", target))
        else:
            print("OK   link  %s" % target)

    if missing:
        print("\nMISSING:")
        for kind, target in missing:
            print("  %s: %s" % (kind, target))
        return 1

    print("\nOK: %d images, %d local links all resolve" % (local_images, local_links))
    return 0


if __name__ == "__main__":
    sys.exit(main())
