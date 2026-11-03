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

    def add_unreleased(self) -> None:
        self.write(FILES[2], self.read(FILES[2]).replace(
            "\n## [", "\n## [Unveröffentlicht]\n\n### Verbessert\n- etwas\n\n## [", 1))


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

    def test_against_compares_with_the_given_file_not_the_checkout(self):
        # A release commit already carries the new version; "newer" must be
        # measured against main's config.yaml, which the workflow hands over.
        main = self.root / "main-config.yaml"
        main.write_text('version: "5.0.0"\n', encoding="utf-8")
        self.assertEqual(run(self.root, "5.0.1", "--check-newer", "--against", str(main)).returncode, 0)
        self.assertNotEqual(run(self.root, "5.0.0", "--check-newer", "--against", str(main)).returncode, 0)
        self.assertNotEqual(run(self.root, "4.9.9", "--check-newer", "--against", str(main)).returncode, 0)
        self.assertUnchanged()

    def test_against_alone_is_refused(self):
        # Without a comparison it would silently set the version.
        main = self.root / "main-config.yaml"
        main.write_text('version: "5.0.0"\n', encoding="utf-8")
        result = run(self.root, "5.0.1", "--against", str(main))
        self.assertNotEqual(result.returncode, 0)
        self.assertUnchanged()


class TestVerify(OnACopy):
    """--verify is what the build runs on the tag: is this the release commit?"""

    def setUp(self):
        super().setUp()
        # main's config.yaml before the release, as the workflow fetches it
        shutil.copy(self.root / FILES[0], self.root / "main-config.yaml")
        self.add_unreleased()
        self.assertEqual(run(self.root, "98.7.6", "--require-unreleased").returncode, 0)
        self.release_files = {name: self.read(name) for name in FILES}

    def verify(self, version: str = "98.7.6") -> subprocess.CompletedProcess[str]:
        return run(self.root, version, "--verify", "--against", str(self.root / "main-config.yaml"))

    def test_accepts_a_release_commit_and_writes_nothing(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({name: self.read(name) for name in FILES}, self.release_files)

    def test_refuses_a_checkout_whose_config_has_the_old_version(self):
        # A tag on plain main: nothing was prepared, the image would be built
        # under a version number the files do not carry.
        self.write(FILES[0], (ROOT / FILES[0]).read_text(encoding="utf-8"))
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("config.yaml says", result.stderr)

    def test_refuses_when_the_package_version_differs(self):
        self.write(FILES[1], (ROOT / FILES[1]).read_text(encoding="utf-8"))
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("__init__.py says", result.stderr)

    def test_refuses_an_undated_changelog(self):
        # The point of the release commit: the tag shows the finished CHANGELOG.
        self.write(FILES[2], self.read(FILES[2]).replace("## [98.7.6] - ", "## [Unveröffentlicht] - ", 1))
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no dated section", result.stderr)

    def test_refuses_a_version_that_is_not_newer_than_main(self):
        # Publishing a version again must not get as far as overwriting its image.
        (self.root / "main-config.yaml").write_text('version: "98.7.6"\n', encoding="utf-8")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_allow_same_accepts_main_already_on_the_version(self):
        # A re-run of the ZIP job after the release went onto main.
        (self.root / "main-config.yaml").write_text('version: "98.7.6"\n', encoding="utf-8")
        result = run(self.root, "98.7.6", "--verify", "--allow-same",
                     "--against", str(self.root / "main-config.yaml"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_allow_same_still_refuses_a_version_older_than_main(self):
        (self.root / "main-config.yaml").write_text('version: "98.7.7"\n', encoding="utf-8")
        result = run(self.root, "98.7.6", "--verify", "--allow-same",
                     "--against", str(self.root / "main-config.yaml"))
        self.assertNotEqual(result.returncode, 0)

    def test_allow_same_does_not_loosen_the_other_checks(self):
        (self.root / "main-config.yaml").write_text('version: "98.7.6"\n', encoding="utf-8")
        self.write(FILES[2], self.read(FILES[2]).replace("## [98.7.6] - ", "## [Unveröffentlicht] - ", 1))
        result = run(self.root, "98.7.6", "--verify", "--allow-same",
                     "--against", str(self.root / "main-config.yaml"))
        self.assertNotEqual(result.returncode, 0)

    def test_allow_same_only_belongs_to_verify(self):
        result = run(self.root, "98.7.6", "--check-newer", "--allow-same")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--allow-same", result.stderr)

    def test_refuses_the_tag_naming_another_version_than_the_files(self):
        self.assertNotEqual(self.verify("98.7.7").returncode, 0)

    def test_needs_something_to_compare_with(self):
        result = run(self.root, "98.7.6", "--verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--against", result.stderr)


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

    def test_require_unreleased_fails_before_writing_anything(self):
        # The release commit exists to carry a dated section. Without one the
        # prepare workflow must stop, not push a version with an empty CHANGELOG.
        self.write(FILES[2], self.read(FILES[2]).replace("## [Unveröffentlicht]", ""))
        before = {name: self.read(name) for name in FILES}

        result = run(self.root, "98.7.6", "--require-unreleased")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nothing to release", result.stderr)
        self.assertEqual({name: self.read(name) for name in FILES}, before)

    def test_require_unreleased_still_sets_everything_when_there_is_a_section(self):
        self.add_unreleased()
        result = run(self.root, "98.7.6", "--require-unreleased")
        self.assertEqual(result.returncode, 0, result.stderr)
        today = datetime.date.today().isoformat()
        self.assertIn(f"\n## [98.7.6] - {today}\n", self.read(FILES[2]))
        self.assertIn('\nversion: "98.7.6"\n', self.read(FILES[0]))

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
