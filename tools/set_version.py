#!/usr/bin/env python3
"""Set the release version everywhere it is written down.

WHY THE RELEASE WORKFLOW DOES THIS, NOT A PERSON

The Supervisor reads `version` in dnsmith/config.yaml straight from main, not
from a GitHub release. Raising it on main offers every installation an update
at once, whether or not the image for that version exists yet. On 2026-10-26
that is exactly what happened: 0.1.4 sat on main, the update banner showed,
and ghcr.io answered 404 for the image it would have pulled.

So nobody raises the version by hand. The workflow "Release vorbereiten"
(release-prepare.yml) runs this on a copy of main, commits the result as the
release commit R on the branch release/X.Y.Z (NOT on main) and opens a draft
release whose target is R. Publishing the draft puts the tag on R, so the tag,
the image and the ZIP all carry the new version and the dated CHANGELOG. Home
Assistant never sees R: it reads main. Only after both images are on ghcr.io
does the last release job bring R onto main, and the update appears.

    python3 tools/set_version.py 0.1.5 --require-unreleased
                                          write config.yaml, __init__.py and
                                          date the CHANGELOG section; fail
                                          before writing anything if there is
                                          no "## [Unveröffentlicht]" section
    python3 tools/set_version.py 0.1.5 --check-newer
                                          fail unless 0.1.5 is newer than the
                                          version in config.yaml
    python3 tools/set_version.py 0.1.5 --verify --against main-config.yaml
                                          writes nothing; fail unless config.yaml,
                                          __init__.py and the CHANGELOG all
                                          carry 0.1.5 (a release commit) and
                                          0.1.5 is newer than the version in
                                          the given config.yaml (main's);
                                          --allow-same also accepts equal

The CHANGELOG collects changes under "## [Unveröffentlicht]"; this turns that
heading into "## [0.1.5] - <today>". Without --require-unreleased and without
such a section it changes nothing there.

PRE-RELEASES

A pre-release is for testing from the ZIP or a folder copy and must not
reach Home Assistant as an update until it is switched to a full release on
GitHub. It is made from the same release commit R (v0.1.5, no suffix:
switching it over must not need a new tag). Nothing is written to main until
the switch; R then goes onto main as it is.
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


def current(config: pathlib.Path = CONFIG) -> str:
    match = CONFIG_LINE.search(config.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"{config}: no line 'version: \"...\"'")
    return match.group(1)


def verify(version: str) -> None:
    """Exit unless this checkout is a release commit for `version`."""
    problems = []
    if current() != version:
        problems.append(f"{CONFIG.name} says {current()}")
    init = INIT_LINE.search(INIT.read_text(encoding="utf-8"))
    if not init or init.group(1) != version:
        problems.append(f"{INIT.name} says {init.group(1) if init else 'nothing'}")
    heading = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", re.M)
    if not heading.search(CHANGELOG.read_text(encoding="utf-8")):
        problems.append(f"{CHANGELOG.name} has no dated section for {version}")
    if problems:
        sys.exit(f"not a release commit for {version}: " + "; ".join(problems))


def replace_one(path: pathlib.Path, pattern: re.Pattern[str], line: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, count = pattern.subn(line, text)
    if count != 1:
        sys.exit(f"{path}: expected one version line, found {count}")
    path.write_text(new, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="X.Y.Z, a leading v is dropped")
    parser.add_argument("--check-newer", action="store_true",
                        help="only compare, write nothing")
    parser.add_argument("--verify", action="store_true",
                        help="only check that this checkout is the release commit")
    parser.add_argument("--against", type=pathlib.Path, metavar="CONFIG_YAML",
                        help="with --check-newer/--verify: compare with the version "
                             "in this config.yaml (main's) instead of the checkout's")
    parser.add_argument("--allow-same", action="store_true",
                        help="with --verify: main may already be on this version "
                             "(re-run of a job that only attaches files)")
    parser.add_argument("--require-unreleased", action="store_true",
                        help="fail unless the CHANGELOG has an Unveröffentlicht section")
    args = parser.parse_args()

    version = args.version.removeprefix("v")
    if not VERSION.match(version):
        sys.exit(f"not a version: {args.version!r} (expected X.Y.Z, a pre-release "
                 f"takes the plain version too)")
    if args.against and not (args.check_newer or args.verify):
        sys.exit("--against only makes sense with --check-newer or --verify")
    if args.verify and not args.against:
        sys.exit("--verify needs --against: the checkout already carries the new "
                 "version, so it cannot be compared with itself")
    if args.allow_same and not args.verify:
        sys.exit("--allow-same only makes sense with --verify")

    if args.check_newer or args.verify:
        base = args.against or CONFIG
        # --allow-same: a re-run of the ZIP job after the release has gone onto
        # main finds main already on this version. Older is still refused.
        too_old = parts(version) < parts(current(base)) if args.allow_same \
            else parts(version) <= parts(current(base))
        if too_old:
            sys.exit(f"{version} is not newer than {current(base)} in {base}")
        if args.verify:
            verify(version)
        return 0

    log = CHANGELOG.read_text(encoding="utf-8")
    if args.require_unreleased and UNRELEASED not in log:
        # ASCII only: a Windows console would not carry the umlaut through
        sys.exit(f"{CHANGELOG.name} has no unreleased section: nothing to release")

    replace_one(CONFIG, CONFIG_LINE, f'version: "{version}"')
    replace_one(INIT, INIT_LINE, f'__version__ = "{version}"')

    if UNRELEASED in log:
        today = datetime.date.today().isoformat()
        log = log.replace(UNRELEASED, f"## [{version}] - {today}", 1)
        CHANGELOG.write_text(log, encoding="utf-8", newline="\n")

    print(f"version set to {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
