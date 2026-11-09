"""The Claude Code plugin and the MCP registry entry point at this release of Petra.

The repository is a Claude Code marketplace: .claude-plugin/marketplace.json lists the
plugin in plugins/petra, which starts the server with uvx and carries the skill that
`petra docs skill` prints. server.json is the entry for the official MCP registry. Each
names a version of petra-lang on PyPI, so each must move with pyproject.toml.
"""
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
PLUGIN = ROOT / "plugins" / "petra"
SKILL = ROOT / "petra" / "docs" / "skill.md"
PIN = re.compile(r"petra-lang(?:==|@)([0-9][0-9A-Za-z.]*)")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Plugin(unittest.TestCase):
    def test_the_plugin_skill_is_petras_skill(self):
        self.assertEqual((PLUGIN / "skills" / "petra" / "SKILL.md").read_bytes(), SKILL.read_bytes(),
                         "copy petra/docs/skill.md to plugins/petra/skills/petra/SKILL.md")

    def test_the_marketplace_serves_the_plugin_by_its_own_name(self):
        (entry,) = read_json(ROOT / ".claude-plugin" / "marketplace.json")["plugins"]
        manifest = read_json(ROOT / entry["source"] / ".claude-plugin" / "plugin.json")
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual((ROOT / entry["source"]).resolve(), PLUGIN.resolve())

    def test_the_skill_gives_the_server_entry_the_plugin_runs(self):
        block = re.search(r"```json\n(.*?)\n```", SKILL.read_text(encoding="utf-8"), re.S).group(1)
        self.assertEqual(json.loads(block), read_json(PLUGIN / ".mcp.json"))

    def test_every_install_line_and_manifest_names_this_release(self):
        pinned = {}
        for path in (PLUGIN / ".mcp.json", SKILL, ROOT / "docs" / "in_the_loop.md", ROOT / "README.md"):
            for version in PIN.findall(path.read_text(encoding="utf-8")):
                pinned.setdefault(version, []).append(path.relative_to(ROOT).as_posix())
        self.assertEqual(set(pinned), {VERSION}, f"pins of petra-lang, by version: {pinned}")
        self.assertEqual(read_json(PLUGIN / ".claude-plugin" / "plugin.json")["version"], VERSION)


class Registry(unittest.TestCase):
    """The registry takes a PyPI package only if its README names the server."""

    def test_the_entry_runs_petra_lang_mcp_from_pypi(self):
        server = read_json(ROOT / "server.json")
        (package,) = server["packages"]
        self.assertEqual((package["registryType"], package["identifier"]), ("pypi", "petra-lang"))
        self.assertEqual(package["transport"], {"type": "stdio"})
        self.assertEqual([a["value"] for a in package["packageArguments"]], ["mcp"])
        self.assertEqual((server["version"], package["version"]), (VERSION, VERSION))
        self.assertLessEqual(len(server["description"]), 100, "the registry's schema caps a description at 100")

    def test_the_readme_names_the_server_for_the_registry(self):
        name = read_json(ROOT / "server.json")["name"]
        self.assertEqual(name, "io.github.NooterraLabs/petra")
        self.assertIn(f"mcp-name: {name}", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
