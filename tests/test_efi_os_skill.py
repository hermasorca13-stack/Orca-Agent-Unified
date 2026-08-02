"""
Tests for skills/efi_os_skill.py.

These tests load the wrapper via importlib (bypassing skills/__init__.py)
and exercise its public API against the bundled tools/EFI_OS.py.

The integrity check, capabilities(), and self_test() calls actually
invoke the bundled CLI subprocess — so these tests are integration
tests by nature. Mocked subprocess tests live in a separate class.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "efi_os_skill.py"
TOOL_PATH = ROOT / "tools" / "EFI_OS.py"
EXPECTED_SHA = "abac459e74f23e1e7f796b899ec54af976fe07797923040a4d6b5fd65c5deace"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "efi_os_skill_under_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["efi_os_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------
# Integrity
# ----------------------------------------------------------------------
class TestIntegrity:
    def test_tool_file_exists(self):
        assert TOOL_PATH.exists(), (
            f"Bundled EFI-OS not found at {TOOL_PATH}"
        )

    def test_sha256_constant_matches_documented(self):
        mod = _load_skill()
        assert mod.EFI_SHA256 == EXPECTED_SHA

    def test_skill_loads_without_error(self):
        # Importing the module runs _verify_integrity; any failure
        # raises EFIOSTamperedError, which would surface here.
        mod = _load_skill()
        assert mod.EFI_PATH == TOOL_PATH

    def test_path_is_absolute(self):
        mod = _load_skill()
        assert mod.EFI_PATH.is_absolute()

    def test_subcommands_list_non_empty(self):
        mod = _load_skill()
        assert "self-test" in mod.SUB_COMMANDS
        assert "capabilities" in mod.SUB_COMMANDS
        assert "analyze" in mod.SUB_COMMANDS
        assert "research" in mod.SUB_COMMANDS


# ----------------------------------------------------------------------
# Live integration (real subprocess, no mocks)
# ----------------------------------------------------------------------
@pytest.mark.skipif(
    not TOOL_PATH.exists(),
    reason="Bundled EFI-OS not found at tools/EFI_OS.py",
)
class TestLive:
    def test_capabilities_returns_known_keys(self):
        mod = _load_skill()
        cap = mod.capabilities()
        assert cap["service"] == "EFI-OS"
        assert cap["single_file"] is True
        assert cap["external_api_keys_required"] is False
        assert isinstance(cap["capabilities"], dict)
        assert len(cap["capabilities"]) >= 10

    def test_self_test_19_pass(self):
        mod = _load_skill()
        st = mod.self_test()
        assert st["total"] >= 19
        assert st["failed"] == 0
        assert st["ok"] == 19
        assert st["returncode"] == 0

    def test_run_unknown_subcommand_rejected(self):
        mod = _load_skill()
        with pytest.raises(mod.EFIOSError, match="Unknown EFI-OS"):
            mod.run("totally-bogus-subcommand")

    def test_run_self_test_returns_tuple(self):
        mod = _load_skill()
        rc, out, err = mod.run("self-test", timeout=60.0)
        # self-test may exit non-zero only on a real failure.
        # We just verify the tuple shape.
        assert isinstance(rc, int)
        assert isinstance(out, str)
        assert isinstance(err, str)
        assert rc == 0
        assert "ok" in (out + err)


# ----------------------------------------------------------------------
# Mocked subprocess path (no real CLI call)
# ----------------------------------------------------------------------
class TestMocked:
    def test_run_returns_tuple(self):
        mod = _load_skill()
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = '{"ok": true}'
        fake.stderr = ''
        with patch.object(mod.subprocess, "run", return_value=fake):
            rc, out, err = mod._run("self-test")
        assert rc == 0
        assert "ok" in out

    def test_run_json_parses_stdout(self):
        mod = _load_skill()
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = '{"service": "EFI-OS", "single_file": true}'
        fake.stderr = ''
        with patch.object(mod.subprocess, "run", return_value=fake):
            data = mod._run_json("capabilities")
        assert data["service"] == "EFI-OS"
        assert data["single_file"] is True

    def test_run_json_tolerates_garbage_prefix(self):
        mod = _load_skill()
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = 'WARNING: something\n{"service": "X"}'
        fake.stderr = ''
        with patch.object(mod.subprocess, "run", return_value=fake):
            data = mod._run_json("capabilities")
        assert data["service"] == "X"

    def test_run_json_nonzero_exit_raises(self):
        mod = _load_skill()
        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ''
        fake.stderr = 'fatal: something went wrong'
        with patch.object(mod.subprocess, "run", return_value=fake):
            with pytest.raises(mod.EFIOSError, match="returned 1"):
                mod._run_json("capabilities")

    def test_run_json_no_json_raises(self):
        mod = _load_skill()
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = 'no JSON here at all'
        fake.stderr = ''
        with patch.object(mod.subprocess, "run", return_value=fake):
            with pytest.raises(mod.EFIOSError, match="no JSON"):
                mod._run_json("capabilities")

    def test_run_timeout_maps_to_friendly_error(self):
        mod = _load_skill()
        with patch.object(mod.subprocess, "run",
                          side_effect=__import__("subprocess").TimeoutExpired(
                              "cmd", 60)):
            with pytest.raises(mod.EFIOSError, match="timed out"):
                mod._run("self-test", timeout=5.0)

    def test_run_filenotfound_maps_to_friendly_error(self):
        mod = _load_skill()
        with patch.object(mod.subprocess, "run",
                          side_effect=FileNotFoundError("no such python")):
            with pytest.raises(mod.EFIOSError, match="Could not launch"):
                mod._run("self-test")


# ----------------------------------------------------------------------
# Format helper
# ----------------------------------------------------------------------
class TestFormat:
    def test_format_capabilities(self):
        mod = _load_skill()
        cap = {
            "service": "EFI-OS",
            "single_file": True,
            "external_api_keys_required": False,
            "capabilities": {"a_b": "first", "c_d": "second"},
        }
        out = mod.format_capabilities(cap)
        assert "EFI-OS" in out
        assert "first" in out
        assert "second" in out
        assert "01" in out  # numbering


# ----------------------------------------------------------------------
# Tamper detection (synthetic)
# ----------------------------------------------------------------------
class TestTamper:
    def test_sha_mismatch_raises_on_import(self, tmp_path, monkeypatch):
        # Create a fake skills/efi_os_skill.py that points at a
        # mismatched EFI-OS file. We import it in isolation.
        fake_tool = tmp_path / "EFI_OS.py"
        fake_tool.write_bytes(b"# fake\n")
        fake_skill = tmp_path / "efi_os_skill.py"
        # Substitute the EFI_PATH lookup so it points at our fake.
        fake_skill.write_text(
            "from pathlib import Path\n"
            "import hashlib\n"
            "EFI_PATH = Path(r'%s')\n"
            "EFI_SHA256 = '0000000000000000000000000000000000000000000000000000000000000000'\n"
            "class EFIOSTamperedError(RuntimeError): pass\n"
            "class EFIOSError(RuntimeError): pass\n"
            "def _verify_integrity():\n"
            "    if not EFI_PATH.exists():\n"
            "        raise EFIOSTamperedError('missing')\n"
            "    actual = hashlib.sha256(EFI_PATH.read_bytes()).hexdigest()\n"
            "    if actual != EFI_SHA256:\n"
            "        raise EFIOSTamperedError('sha mismatch')\n"
            "_verify_integrity()\n" % str(fake_tool)
        )
        spec = importlib.util.spec_from_file_location(
            "fake_efi_skill", str(fake_skill))
        with pytest.raises(Exception) as ei:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        # The exception class name is preserved even if the import
        # path differs.
        assert "Tampered" in ei.value.__class__.__name__ or \
               "sha mismatch" in str(ei.value) or \
               "mismatch" in str(ei.value).lower()
