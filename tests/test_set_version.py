"""tools/set_version.py, which the release workflows run instead of a person.

It only runs when a release is published, so a version line it can no longer
find would first show up as a failed release. These tests run it on a fresh
copy of the real files: does it still find every line, and does it write the
right thing and nothing else?
"""

from __future__ import annotations

import datetime
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "set_version.py"
FILES = (
    "dnsmith/config.yaml",
    "dnsmith/hub/dnsmith_hub/__init__.py",
    "dnsmith/CHANGELOG.md",
)


def run(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "tools" / "set_version.py"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


class OnACopy(unittest.TestCase):
    # Even the checks only run on a copy: a script that wrote where it should
    # only compare would otherwise raise the real version, by hand, unnoticed.
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "tools").mkdir()
        shutil.copy(SCRIPT, self.root / "tools")
        for name in FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, target)

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def write(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8")

    def assertUnchanged(self) -> None:
        for name in FILES:
            self.assertEqual(self.read(name), (ROOT / name).read_text(encoding="utf-8"), name)


class TestCheckNewer(OnACopy):
    def test_finds_the_version_in_config_yaml_and_writes_nothing(self):
        result = run(self.root, "999.0.0", "--check-newer")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertUnchanged()

    def test_refuses_a_version_that_is_not_newer(self):
        result = run(self.root, "0.0.1", "--check-newer")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not newer", result.stderr)

    def test_compares_numbers_not_text(self):
        # As text "0.1.9" sorts after "0.1.10": a late switch of an old
        # pre-release would set main back.
        config = self.read(FILES[0])
        current = config.split('\nversion: "', 1)[1].split('"', 1)[0]
        self.write(FILES[0], config.replace(f'version: "{current}"', 'version: "0.1.10"', 1))
        self.assertNotEqual(run(self.root, "0.1.9", "--check-newer").returncode, 0)
        self.assertEqual(run(self.root, "0.1.11", "--check-newer").returncode, 0)

    def test_refuses_the_version_already_on_main(self):
        # Publishing the same version again would overwrite its image tag.
        config = self.read(FILES[0])
        current = config.split('\nversion: "', 1)[1].split('"', 1)[0]
        result = run(self.root, current, "--check-newer")
        self.assertNotEqual(result.returncode, 0)


class TestSetVersion(OnACopy):
    def test_sets_config_and_package_version(self):
        result = run(self.root, "v98.7.6")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\nversion: "98.7.6"\n', self.read(FILES[0]))
        self.assertIn('\n__version__ = "98.7.6"\n', self.read(FILES[1]))

    def test_dates_the_unreleased_section_and_nothing_else(self):
        log = self.read(FILES[2]).replace(
            "\n## [", "\n## [Unveröffentlicht]\n\n### Verbessert\n- etwas\n\n## [", 1)
        self.write(FILES[2], log)

        run(self.root, "98.7.6")

        today = datetime.date.today().isoformat()
        expected = log.replace("## [Unveröffentlicht]", f"## [98.7.6] - {today}", 1)
        self.assertEqual(self.read(FILES[2]), expected)

    def test_leaves_the_changelog_alone_without_an_unreleased_section(self):
        before = self.read(FILES[2]).replace("## [Unveröffentlicht]", "")
        self.write(FILES[2], before)

        run(self.root, "98.7.6")

        self.assertEqual(self.read(FILES[2]), before)

    def test_a_prerelease_sets_the_version_and_leaves_the_changelog(self):
        # Switched to a full release later, the same tag must still fit, so a
        # pre-release takes the plain version; only the CHANGELOG waits.
        log = self.read(FILES[2]).replace(
            "\n## [", "\n## [Unveröffentlicht]\n\n- etwas\n\n## [", 1)
        self.write(FILES[2], log)

        result = run(self.root, "v98.7.6", "--prerelease")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\nversion: "98.7.6"\n', self.read(FILES[0]))
        self.assertIn('\n__version__ = "98.7.6"\n', self.read(FILES[1]))
        self.assertEqual(self.read(FILES[2]), log)

    def test_rejects_something_that_is_not_a_version(self):
        # A suffix included: a pre-release tagged v0.1.5-beta.1 could never
        # be switched to the full release 0.1.5.
        for tag in ("0.1", "v0.1.5-beta.1"):
            with self.subTest(tag=tag):
                result = run(self.root, tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not a version", result.stderr)
                self.assertUnchanged()


if __name__ == "__main__":
    unittest.main()
