"""Petra installs offline from its own build backend and runs from any directory.

setUpClass builds the wheel through pip from this tree (build isolation on, no index),
the sdist through the backend's hook, and a second wheel through pip from that sdist,
then installs the first wheel into a fresh venv. The tests check what the wheel ships,
that the sdist rebuilds the same wheel, and that the installed `petra` command answers,
and prints its documents, from a directory outside the repository, as it would for a
stranger.
"""
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
DIST = PROJECT["name"].replace("-", "_")
DIST_INFO = f"{DIST}-{PROJECT['version']}.dist-info"
OFFLINE = ("--disable-pip-version-check", "--no-index", "--no-deps", "--no-cache-dir")

# A stranger has no pip configuration of ours, no shapes workbook and no repository on sys.path.
ENV = {k: v for k, v in os.environ.items() if not k.startswith("PIP_") and k not in ("PETRA_SHAPES_XLSX", "PYTHONPATH")}
ENV["PIP_CONFIG_FILE"] = os.devnull


def run(*argv: str | Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(a) for a in argv], cwd=cwd, env=ENV, capture_output=True, text=True, timeout=300)


def ok(*argv: str | Path, cwd: Path) -> str:
    done = run(*argv, cwd=cwd)
    if done.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, argv))} exited {done.returncode}\n{done.stdout}\n{done.stderr}")
    return done.stdout


def venv(where: Path) -> tuple[Path, Path]:
    """A fresh venv that sees the base install's numpy, scipy and pip. Its own pip would
    cost ensurepip about 20 s on Windows. Returns (python, scripts directory)."""
    ok(sys.executable, "-m", "venv", "--system-site-packages", "--without-pip", where, cwd=where.parent)
    scripts = where / ("Scripts" if os.name == "nt" else "bin")
    return Path(shutil.which("python", path=str(scripts))), scripts


def backend():
    spec = importlib.util.spec_from_file_location("petra_build", ROOT / "_build" / "petra_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Packaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="petra-packaging-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        tree, from_sdist = cls.tmp / "tree", cls.tmp / "from_sdist"
        ok(sys.executable, "-m", "pip", "wheel", *OFFLINE, "-w", tree, ROOT, cwd=cls.tmp)
        cls.sdist = cls.tmp / backend().build_sdist(str(cls.tmp))
        ok(sys.executable, "-m", "pip", "wheel", *OFFLINE, "-w", from_sdist, cls.sdist, cwd=cls.tmp)
        (cls.wheel,) = tree.glob("*.whl")
        (cls.sdist_wheel,) = from_sdist.glob("*.whl")
        with zipfile.ZipFile(cls.wheel) as archive:
            cls.files = {name: archive.read(name) for name in archive.namelist()}
        cls.python, cls.scripts = venv(cls.tmp / "venv")
        ok(cls.python, "-m", "pip", "install", *OFFLINE, "--no-compile", cls.wheel, cwd=cls.tmp)
        cls.outside = cls.tmp / "elsewhere"
        cls.outside.mkdir()

    def test_the_wheel_ships_every_tracked_package_file_and_nothing_else(self):
        listed = subprocess.run(["git", "ls-files", "-z", "petra"], cwd=ROOT, capture_output=True)
        if listed.returncode != 0:
            self.skipTest("not a git checkout")
        tracked = set(listed.stdout.decode("utf-8").split("\0")) - {""}
        self.assertIn("petra/registry/aisc_shapes.json", tracked, "the shapes table is tracked")
        self.assertIn("petra/docs/api.md", tracked, "the API document is tracked")
        self.assertEqual(tracked - set(self.files), set(), "the wheel ships every tracked file under petra/, data files included")
        stray = {n for n in self.files if not n.startswith(("petra/", f"{DIST_INFO}/"))}
        self.assertEqual(stray, set(), "the wheel ships only the package and its .dist-info")

    def test_the_wheel_metadata_names_petra_its_licence_and_its_dependencies(self):
        meta = BytesParser().parsebytes(self.files[f"{DIST_INFO}/METADATA"])
        self.assertEqual((meta["Name"], meta["Version"]), ("petra-lang", PROJECT["version"]))
        self.assertEqual(meta["Requires-Python"], ">=3.11")
        self.assertEqual(meta["License-Expression"], "Apache-2.0")
        self.assertEqual({d.split(">=")[0] for d in meta.get_all("Requires-Dist")}, {"numpy", "scipy"})
        self.assertEqual(self.files[f"{DIST_INFO}/licenses/LICENSE"], (ROOT / "LICENSE").read_bytes())
        scripts = self.files[f"{DIST_INFO}/entry_points.txt"].decode("utf-8").splitlines()
        self.assertLess({"petra = petra.cli:main", "petra-lang = petra.cli:main"}, set(scripts))
        self.assertIn("Source, https://github.com/NooterraLabs/petra", meta.get_all("Project-URL"))

    def test_the_published_readme_links_into_the_repository_at_the_release_tag(self):
        published = BytesParser().parsebytes(self.files[f"{DIST_INFO}/METADATA"]).get_payload()
        targets = re.findall(r"\]\(([^)\s]+)\)", published)
        self.assertEqual([t for t in targets if not t.startswith(("https://", "http://", "#"))], [],
                         "no link is relative, because PyPI and an installed petra have no repository beside them")
        tag = f"https://github.com/NooterraLabs/petra/blob/v{PROJECT['version']}/"
        self.assertIn(f"]({tag}docs/plan.md)", published)
        self.assertEqual(re.sub(re.escape(tag), "", published), (ROOT / "README.md").read_text(encoding="utf-8"),
                         "only the link targets differ from README.md")

    def test_every_wheel_file_matches_its_record_row(self):
        rows = list(csv.reader(io.StringIO(self.files[f"{DIST_INFO}/RECORD"].decode("utf-8"))))
        self.assertEqual({r[0] for r in rows}, set(self.files), "RECORD lists every file once")
        for path, digest, size in rows:
            if path == f"{DIST_INFO}/RECORD":
                continue
            data = self.files[path]
            expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
            self.assertEqual((digest, int(size)), (expected, len(data)), path)

    def test_the_sdist_builds_the_same_wheel_byte_for_byte(self):
        self.assertEqual(self.sdist.name, f"{DIST}-{PROJECT['version']}.tar.gz")
        self.assertEqual(self.sdist_wheel.read_bytes(), self.wheel.read_bytes())

    def test_the_installed_command_runs_outside_the_repository(self):
        petra = shutil.which("petra", path=str(self.scripts))
        self.assertIsNotNone(petra, "pip installed the petra command")
        self.assertEqual(run(petra, "--help", cwd=self.outside).returncode, 0)
        done = run(petra, "check", ROOT / "examples" / "steel" / "shear_tab.petra", cwd=self.outside)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0], "steel-shear-tab: PASS")
        where, *versions = ok(self.python, "-c", "import importlib.metadata, petra; print(petra.__file__); "
                              "print(importlib.metadata.version('petra-lang')); print(petra.__version__)", cwd=self.outside).splitlines()
        self.assertTrue(Path(where).resolve().is_relative_to((self.tmp / "venv").resolve()), f"petra imports from the venv, not {where}")
        self.assertEqual(versions, [PROJECT["version"]] * 2, "the installed metadata and petra.__version__ match pyproject.toml")

    def test_the_installed_command_prints_its_documents_outside_the_repository(self):
        petra = shutil.which("petra", path=str(self.scripts))
        self.assertIn("`petra docs`", ok(petra, "--help", cwd=self.outside).rstrip("\n").splitlines()[-1])
        listed = [line.split()[0] for line in ok(petra, "docs", cwd=self.outside).splitlines()[:-1]]
        self.assertEqual(listed, ["readme", "reference", "api", "skill"])
        for name, text in (("api", (ROOT / "petra" / "docs" / "api.md").read_text(encoding="utf-8")),
                           ("reference", (ROOT / "docs" / "reference.md").read_text(encoding="utf-8")),
                           ("readme", backend().description(PROJECT))):
            with self.subTest(name):
                self.assertEqual(ok(petra, "docs", name, cwd=self.outside), text)

    def test_the_command_named_for_the_package_serves_mcp(self):
        """`uvx petra-lang mcp` runs the executable named petra-lang. That is the command
        a client builds from the MCP registry's entry, which names the package."""
        command = shutil.which("petra-lang", path=str(self.scripts))
        self.assertIsNotNone(command, "pip installed the petra-lang command")
        hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
        done = subprocess.run([command, "mcp"], input=json.dumps(hello) + "\n", cwd=self.outside, env=ENV,
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(json.loads(done.stdout)["result"]["serverInfo"], {"name": "petra", "version": PROJECT["version"]})

    def test_an_editable_install_imports_the_source_tree(self):
        python, _ = venv(self.tmp / "editable")
        ok(python, "-m", "pip", "install", *OFFLINE, "--no-compile", "-e", ROOT, cwd=self.tmp)
        where = ok(python, "-c", "import petra; print(petra.__file__)", cwd=self.outside).strip()
        self.assertEqual(Path(where).resolve(), (ROOT / "petra" / "__init__.py").resolve())
        for name, path in (("api", ROOT / "petra" / "docs" / "api.md"), ("readme", ROOT / "README.md")):
            with self.subTest(name):
                self.assertEqual(ok(python, "-m", "petra", "docs", name, cwd=self.outside), path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
