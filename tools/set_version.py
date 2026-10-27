#!/usr/bin/env python3
"""Set the release version everywhere it is written down.

WHY THE RELEASE WORKFLOW DOES THIS, NOT A PERSON

The Supervisor reads `version` in dnsmith/config.yaml straight from main, not
from a GitHub release. Raising it on main offers every installation an update
at once, whether or not the image for that version exists yet. On 2026-10-26
that is exactly what happened: 0.1.4 sat on main, the update banner showed,
and ghcr.io answered 404 for the image it would have pulled.

So nobody raises the version by hand any more. Publishing release vX.Y.Z runs
this on the tagged checkout, so the image and the ZIP carry the new version
(the User-Agent is built from __version__), and once more after both images
are pushed, for the commit on main that makes the update appear.

    python3 tools/set_version.py 0.1.5    write config.yaml, __init__.py,
                                          and date the CHANGELOG section
    python3 tools/set_version.py 0.1.5 --check-newer
                                          fail unless 0.1.5 is newer than
                                          the version in config.yaml

The CHANGELOG collects changes under "## [Unveröffentlicht]"; this turns that
heading into "## [0.1.5] - <today>". Without such a section it changes
nothing there.

PRE-RELEASES

A pre-release is for testing from the ZIP or a folder copy and must not
reach Home Assistant as an update until it is switched to a full release on
GitHub. So it takes the plain version (v0.1.5, no suffix: switching it over
must not need a new tag), the workflows pass --prerelease, and nothing is
written to main. --prerelease leaves the CHANGELOG alone: its changes are
still unreleased until the switch.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "dnsmith" / "config.yaml"
INIT = ROOT / "dnsmith" / "hub" / "dnsmith_hub" / "__init__.py"
CHANGELOG = ROOT / "dnsmith" / "CHANGELOG.md"

VERSION = re.compile(r"^\d+\.\d+\.\d+$")
CONFIG_LINE = re.compile(r'^version: "([^"]*)"$', re.M)
INIT_LINE = re.compile(r'^__version__ = "([^"]*)"$', re.M)
UNRELEASED = "## [Unveröffentlicht]"


def parts(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def current() -> str:
    match = CONFIG_LINE.search(CONFIG.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"{CONFIG}: no line 'version: \"...\"'")
    return match.group(1)


def replace_one(path: pathlib.Path, pattern: re.Pattern[str], line: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, count = pattern.subn(line, text)
    if count != 1:
        sys.exit(f"{path}: expected one version line, found {count}")
    path.write_text(new, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="X.Y.Z, a leading v is dropped")
    parser.add_argument("--check-newer", action="store_true")
    parser.add_argument("--prerelease", action="store_true",
                        help="leave the CHANGELOG undated")
    args = parser.parse_args()

    version = args.version.removeprefix("v")
    if not VERSION.match(version):
        sys.exit(f"not a version: {args.version!r} (expected X.Y.Z, a pre-release "
                 f"takes the plain version too)")

    if args.check_newer:
        if parts(version) <= parts(current()):
            sys.exit(f"{version} is not newer than {current()} in {CONFIG.name}")
        return 0

    replace_one(CONFIG, CONFIG_LINE, f'version: "{version}"')
    replace_one(INIT, INIT_LINE, f'__version__ = "{version}"')

    log = CHANGELOG.read_text(encoding="utf-8")
    if UNRELEASED in log and not args.prerelease:
        today = datetime.date.today().isoformat()
        log = log.replace(UNRELEASED, f"## [{version}] - {today}", 1)
        CHANGELOG.write_text(log, encoding="utf-8", newline="\n")

    print(f"version set to {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
