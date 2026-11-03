"""tools/release_to_main.sh, the last step of a release.

It decides whether the release commit R may go onto main, and how. It only runs
when a release is published, and a wrong decision either offers every
installation an update without an image or loses a change on main. So the
cases are replayed here against a local bare repository standing in for GitHub,
with a shallow clone of the tag standing in for the runner.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION = "9.9.9"
TAG = f"v{VERSION}"
COPIED = (
    "dnsmith/config.yaml",
    "dnsmith/hub/dnsmith_hub/__init__.py",
    "dnsmith/CHANGELOG.md",
    "tools/set_version.py",
    "tools/release_to_main.sh",
)


def find_bash() -> str | None:
    # Not the first "bash" on PATH: on Windows that can be the WSL launcher.
    git = shutil.which("git")
    if git:
        candidate = pathlib.Path(git).resolve().parent.parent / "bin" / "bash.exe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("bash")


BASH = find_bash()


@unittest.skipUnless(BASH and shutil.which("git"), "needs bash and git")
class ReleaseToMain(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.origin = self.tmp / "origin.git"
        self.work = self.tmp / "work"
        shim = self.tmp / "shim"
        shim.mkdir()
        # The workflow calls python3; here it must be the interpreter running the tests.
        (shim / "python3").write_text(f'#!/bin/sh\nexec "{pathlib.Path(sys.executable).as_posix()}" "$@"\n')
        self.env = {
            **os.environ,
            "PATH": str(shim) + os.pathsep + os.environ["PATH"],
            "RUNNER_TEMP": str(self.tmp),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(self.tmp, "clone", "-q", self.origin.as_uri(), str(self.work))
        for name in COPIED:
            target = self.work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, target)
        # a CHANGELOG with something to release, a plain old version on main
        log = self.work / "dnsmith/CHANGELOG.md"
        log.write_text(log.read_text(encoding="utf-8").replace(
            "\n## [", "\n## [Unveröffentlicht]\n\n### Verbessert\n- etwas\n\n## [", 1), encoding="utf-8")
        self.commit("main vor dem Release")
        self.git(self.work, "push", "-q", "origin", "HEAD:main")
        self.before = self.rev(self.work, "HEAD")
        # the release commit on its branch, as "Release vorbereiten" makes it
        self.git(self.work, "switch", "-q", "-c", f"release/{VERSION}")
        self.py(self.work, "tools/set_version.py", VERSION, "--require-unreleased")
        self.commit(f"DNSmith {VERSION}: Version gesetzt")
        self.release = self.rev(self.work, "HEAD")
        self.git(self.work, "push", "-q", "origin", f"release/{VERSION}")
        self.git(self.work, "tag", TAG)
        self.git(self.work, "push", "-q", "origin", TAG)
        self.git(self.work, "switch", "-q", "main")

    # --- helpers -------------------------------------------------------
    def git(self, cwd, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True,
                              text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, f"git {' '.join(args)}: {done.stderr}")
        return done.stdout.strip()

    def py(self, cwd, *args: str) -> None:
        done = subprocess.run([sys.executable, *args], cwd=cwd, env=self.env,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)

    def commit(self, message: str) -> None:
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "-q", "-m", message)

    def rev(self, cwd, ref: str) -> str:
        return self.git(cwd, "rev-parse", ref)

    def origin_rev(self, ref: str) -> str:
        return self.rev(self.origin, ref)

    def on_main(self, name: str, text: str, message: str) -> None:
        """A commit that lands on main after the release commit was prepared."""
        self.git(self.work, "switch", "-q", "main")
        target = self.work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self.commit(message)
        self.git(self.work, "push", "-q", "origin", "HEAD:main")

    def run_release(self, depth: int = 2) -> subprocess.CompletedProcess[str]:
        """What the runner does: a shallow checkout of the tag, then the script."""
        # a fresh folder per run: Windows does not always let go of the last one
        self.runs = getattr(self, "runs", 0) + 1
        runner = self.tmp / f"runner{self.runs}"
        self.git(self.tmp, "clone", "-q", f"--depth={depth}", "--branch", TAG,
                 self.origin.as_uri(), str(runner))
        return subprocess.run([BASH, "tools/release_to_main.sh", TAG], cwd=runner,
                              env=self.env, capture_output=True, text=True, encoding="utf-8")

    def main_file(self, name: str) -> str:
        return self.git(self.origin, "show", f"main:{name}")

    def branch_exists(self) -> bool:
        return bool(self.git(self.origin, "branch", "--list", f"release/{VERSION}"))

    # --- the cases -----------------------------------------------------
    def test_main_unmoved_fast_forwards_to_the_release_commit(self):
        result = self.run_release()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        # main IS the tagged commit: same files, same date, no second commit
        self.assertEqual(self.origin_rev("main"), self.release)
        self.assertIn(f'version: "{VERSION}"', self.main_file("dnsmith/config.yaml"))
        self.assertIn(f"## [{VERSION}] - ", self.main_file("dnsmith/CHANGELOG.md"))

    def test_the_release_branch_is_deleted_afterwards(self):
        self.assertTrue(self.branch_exists())
        self.assertEqual(self.run_release().returncode, 0)
        self.assertFalse(self.branch_exists())

    def test_main_that_moved_elsewhere_gets_the_release_commit_on_top(self):
        self.on_main("README.md", "Doku fürs nächste Release\n", "Doku")
        moved = self.origin_rev("main")

        result = self.run_release()

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.git(self.origin, "rev-parse", "main~1"), moved)  # the doc commit is kept
        self.assertEqual(self.main_file("README.md").strip(), "Doku fürs nächste Release")
        # same content as the tag, so same date: no drift between tag and main
        for name in COPIED[:3]:
            self.assertEqual(self.main_file(name), self.git(self.origin, "show", f"{TAG}:{name}"), name)

    def test_changed_changelog_on_main_stops_everything(self):
        # It would date entries that are not in the image.
        self.on_main("dnsmith/CHANGELOG.md", "# Changelog\n\n## [Unveröffentlicht]\n- neu\n", "Eintrag")
        moved = self.origin_rev("main")

        result = self.run_release()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHANGELOG oder config.yaml", result.stdout + result.stderr)
        self.assertEqual(self.origin_rev("main"), moved)
        self.assertTrue(self.branch_exists())  # nothing was cleaned up

    def test_changed_config_on_main_stops_everything(self):
        # The Supervisor reads all of config.yaml from main.
        config = (self.work / "dnsmith/config.yaml").read_text(encoding="utf-8")
        self.on_main("dnsmith/config.yaml", config + "\n# neue Option\n", "Option")
        moved = self.origin_rev("main")

        self.assertNotEqual(self.run_release().returncode, 0)
        self.assertEqual(self.origin_rev("main"), moved)

    def test_main_already_on_the_version_is_left_alone(self):
        # The second run of a release ("released" after "published").
        self.assertEqual(self.run_release().returncode, 0)
        done = self.origin_rev("main")

        result = self.run_release()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("steht schon auf", result.stdout)
        self.assertEqual(self.origin_rev("main"), done)

    def test_a_checkout_without_the_parent_is_refused(self):
        result = self.run_release(depth=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fetch-depth", result.stdout + result.stderr)
        self.assertEqual(self.origin_rev("main"), self.before)

    def test_a_tag_on_plain_main_is_refused(self):
        # Tagged by hand without "Release vorbereiten": the files carry the old
        # version, so nothing may reach main under the new number.
        # (a side commit on top of main that is only ever tagged, never merged)
        self.git(self.work, "switch", "-q", "-c", "plain", "main")
        (self.work / "README.md").write_text("nur ein Tag\n", encoding="utf-8")
        self.commit("ohne Vorbereitung")
        self.git(self.work, "tag", "-f", TAG)
        self.git(self.work, "push", "-q", "-f", "origin", TAG)
        self.git(self.work, "switch", "-q", "main")

        result = self.run_release()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.origin_rev("main"), self.before)

    def test_a_moved_release_branch_is_not_deleted(self):
        # Someone pushed to release/X.Y.Z after the tag: not ours to remove.
        self.git(self.work, "switch", "-q", f"release/{VERSION}")
        (self.work / "notiz.txt").write_text("später\n")
        self.commit("später")
        self.git(self.work, "push", "-q", "origin", f"release/{VERSION}")
        self.git(self.work, "switch", "-q", "main")

        self.assertEqual(self.run_release().returncode, 0)
        self.assertTrue(self.branch_exists())


if __name__ == "__main__":
    unittest.main()
