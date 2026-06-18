"""Tests for the launchd plist (`scripts/com.gundam.halo.plist`).

Sprint 26 §4.2 / Sprint 34 Track 2 — verify the plist XML is
well-formed and the required keys are present. The actual
launchctl load / plutil -lint verification is done by the
install script (we don't shell out here, since plutil may
not be available in the test env).

The plist uses `__HALO_REPO__` and `__HALO_HOME__`
placeholders that the install script substitutes. We
LINT the plist as-is (the placeholders are valid XML
text content) and additionally check that the
placeholder substitution would produce the right
keys.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

# The plist is in <repo_root>/scripts/com.gundam.halo.plist.
# The test file is in <repo_root>/backend/tests/test_launchd_plist.py.
# We resolve the repo root by walking up from this file.
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parent.parent.parent  # tests/ → backend/ → repo
PLIST_PATH = REPO_ROOT / "scripts" / "com.gundam.halo.plist"

# The 2 placeholders the install script substitutes.
PLACEHOLDER_REPO = "__HALO_REPO__"
PLACEHOLDER_HOME = "__HALO_HOME__"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plist_text() -> str:
    """Raw plist XML as a string. Skip the test module if the plist is missing."""
    if not PLIST_PATH.exists():
        pytest.skip(f"Plist not found: {PLIST_PATH}")
    return PLIST_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def plist_root(plist_text: str) -> ET.Element:
    """Parsed plist root element. Skips on malformed XML."""
    try:
        root = ET.fromstring(plist_text)
    except ET.ParseError as e:
        pytest.fail(f"Plist XML is malformed: {e}")
    return root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plist_dict(root: ET.Element) -> ET.Element:
    """Return the top-level <dict> child of <plist>.

    Apple plists are a single <dict> at the top level. All
    keys live inside this dict.
    """
    for child in root:
        if child.tag == "dict":
            return child
    raise AssertionError("No <dict> in <plist>")


def _find_key(root: ET.Element, key: str) -> ET.Element | None:
    """Find a top-level <key>name</key> + value sibling in the plist dict.

    launchd plists are a single <dict> with <key>...</key> /
    value pairs. We walk the children sequentially.
    """
    children = list(_plist_dict(root))
    for i, child in enumerate(children):
        if child.tag == "key" and child.text == key and i + 1 < len(children):
            return children[i + 1]
    return None


def _value_text(elem: ET.Element | None) -> str | None:
    """Get the text content of a plist value element, or None."""
    if elem is None:
        return None
    return elem.text


# ---------------------------------------------------------------------------
# 1. XML well-formedness (lint)
# ---------------------------------------------------------------------------


class TestPlistWellFormed:
    """The plist must be valid XML (and valid plist XML structure)."""

    def test_plist_file_exists(self) -> None:
        assert PLIST_PATH.exists(), f"Plist missing: {PLIST_PATH}"

    def test_plist_is_valid_xml(self, plist_root: ET.Element) -> None:
        # If the fixture resolved, ET.fromstring succeeded.
        # We double-check the root tag.
        assert plist_root.tag == "plist", f"Expected <plist>, got <{plist_root.tag}>"

    def test_plist_root_has_single_dict(self, plist_root: ET.Element) -> None:
        """The plist body is a single <dict> element per Apple's spec."""
        dicts = [c for c in plist_root if c.tag == "dict"]
        assert len(dicts) == 1, f"Expected 1 <dict> in <plist>, got {len(dicts)}"

    def test_plist_passes_plutil_lint_if_available(self, plist_text: str) -> None:
        """Run `plutil -lint` if plutil is on the PATH.

        We only run this on macOS (plutil is bundled with macOS).
        On Linux test envs, the test is skipped — the
        install script's own plutil check is the real gate.
        """
        if shutil.which("plutil") is None:
            pytest.skip("plutil not installed (non-macOS test env)")
        result = subprocess.run(
            ["plutil", "-lint", str(PLIST_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"plutil -lint failed:\n  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# 2. Required launchd keys
# ---------------------------------------------------------------------------


class TestPlistRequiredKeys:
    """The plist must declare the keys the install script + launchd need."""

    def test_label_is_com_gundam_halo(self, plist_root: ET.Element) -> None:
        label = _value_text(_find_key(plist_root, "Label"))
        assert label == "com.gundam.halo", f"Label: {label!r}"

    def test_program_arguments_is_array(self, plist_root: ET.Element) -> None:
        args = _find_key(plist_root, "ProgramArguments")
        assert args is not None, "ProgramArguments missing"
        assert args.tag == "array", f"ProgramArguments tag: {args.tag}"
        items = [c.text for c in args if c.text is not None]
        assert len(items) >= 3, f"ProgramArguments too short: {items}"
        # The first arg must be the uvicorn binary path (placeholder-substituted
        # at install time). It must end in 'uvicorn'.
        first = items[0]
        assert first.endswith("uvicorn"), f"First ProgramArg: {first!r}"

    def test_run_at_load_is_true(self, plist_root: ET.Element) -> None:
        run_at_load = _find_key(plist_root, "RunAtLoad")
        assert run_at_load is not None, "RunAtLoad missing"
        # XML plist: <true/>
        assert run_at_load.tag == "true", f"RunAtLoad tag: {run_at_load.tag}"

    def test_keep_alive_has_successful_exit_false(self, plist_root: ET.Element) -> None:
        """KeepAlive is a dict with SuccessfulExit=false (restart on crash, not clean exit)."""
        keep_alive = _find_key(plist_root, "KeepAlive")
        assert keep_alive is not None, "KeepAlive missing"
        assert keep_alive.tag == "dict", f"KeepAlive tag: {keep_alive.tag}"

        # Walk children of <dict>KeepAlive</dict> for SuccessfulExit
        ka_children = list(keep_alive)
        successful_exit = None
        for i, child in enumerate(ka_children):
            if (
                child.tag == "key"
                and child.text == "SuccessfulExit"
                and i + 1 < len(ka_children)
            ):
                successful_exit = ka_children[i + 1]
        assert successful_exit is not None, "SuccessfulExit missing in KeepAlive"
        assert successful_exit.tag == "false", (
            f"SuccessfulExit should be <false/>, got <{successful_exit.tag}/>"
        )

    def test_working_directory_has_placeholder(self, plist_root: ET.Element) -> None:
        """WorkingDirectory must contain the __HALO_REPO__ placeholder."""
        wd = _value_text(_find_key(plist_root, "WorkingDirectory"))
        assert wd is not None, "WorkingDirectory missing"
        assert PLACEHOLDER_REPO in wd, (
            f"WorkingDirectory missing {PLACEHOLDER_REPO}: {wd!r}"
        )

    def test_standard_out_and_err_paths_present(
        self, plist_root: ET.Element
    ) -> None:
        out = _value_text(_find_key(plist_root, "StandardOutPath"))
        err = _value_text(_find_key(plist_root, "StandardErrorPath"))
        assert out is not None and "launchd" in out, f"StandardOutPath: {out!r}"
        assert err is not None and "launchd" in err, f"StandardErrorPath: {err!r}"
        # Both must end in .log
        assert out.endswith(".log"), f"StandardOutPath not .log: {out!r}"
        assert err.endswith(".log"), f"StandardErrorPath not .log: {err!r}"

    def test_environment_variables_has_halo_home(
        self, plist_root: ET.Element
    ) -> None:
        env = _find_key(plist_root, "EnvironmentVariables")
        assert env is not None, "EnvironmentVariables missing"
        assert env.tag == "dict", f"EnvironmentVariables tag: {env.tag}"

        # Find HALO_HOME key + value
        env_children = list(env)
        halo_home_value = None
        for i, child in enumerate(env_children):
            if (
                child.tag == "key"
                and child.text == "HALO_HOME"
                and i + 1 < len(env_children)
            ):
                halo_home_value = env_children[i + 1].text
        assert halo_home_value == PLACEHOLDER_HOME, (
            f"HALO_HOME in EnvironmentVariables: {halo_home_value!r}"
        )


# ---------------------------------------------------------------------------
# 3. Placeholder substitution (smoke test for install-launchd.sh logic)
# ---------------------------------------------------------------------------


class TestPlistPlaceholderSubstitution:
    """The install script substitutes __HALO_REPO__ and __HALO_HOME__.

    We don't shell out to install-launchd.sh (which is macOS-only
    + has side effects on launchctl). Instead, we replicate the
    awk-based substitution in Python and verify the result is
    well-formed + has the expected paths.
    """

    def test_substitution_replaces_repo_placeholder(self, plist_text: str) -> None:
        target_repo = "/Users/test/workspace/working/gundam-halo"
        rendered = plist_text.replace(PLACEHOLDER_REPO, target_repo)
        assert PLACEHOLDER_REPO not in rendered, (
            "Placeholder __HALO_REPO__ survived substitution"
        )
        # The rendered WorkingDirectory must start with the repo
        assert target_repo in rendered

    def test_substitution_replaces_home_placeholder(self, plist_text: str) -> None:
        target_home = "/Users/test/.gundam-halo"
        rendered = plist_text.replace(PLACEHOLDER_HOME, target_home)
        assert PLACEHOLDER_HOME not in rendered, (
            "Placeholder __HALO_HOME__ survived substitution"
        )
        assert target_home in rendered

    def test_substitution_yields_valid_xml(self, plist_text: str) -> None:
        """A full substitution must still parse as valid XML."""
        rendered = plist_text.replace(PLACEHOLDER_REPO, "/tmp/repo").replace(
            PLACEHOLDER_HOME, "/tmp/home"
        )
        try:
            root = ET.fromstring(rendered)
        except ET.ParseError as e:
            pytest.fail(f"Substituted plist is malformed XML: {e}")
        # And the working directory should now reflect the substitution
        wd = _value_text(_find_key(root, "WorkingDirectory"))
        assert wd is not None and "/tmp/repo" in wd, f"WD after substitution: {wd!r}"

    def test_no_unexpected_placeholders_remain(self, plist_text: str) -> None:
        """Only the two documented placeholders should appear in the plist.

        The install script's awk pattern matches __HALO_REPO__ and
        __HALO_HOME__ — anything else (e.g. __HALO_USER__) would
        be a bug. We use a regex to find all __...__ tokens and
        assert the set is exactly the documented 2.
        """
        placeholders = set(re.findall(r"__[A-Z_]+__", plist_text))
        expected = {PLACEHOLDER_REPO, PLACEHOLDER_HOME}
        assert placeholders == expected, (
            f"Unexpected placeholders: {placeholders - expected}, "
            f"missing: {expected - placeholders}"
        )
