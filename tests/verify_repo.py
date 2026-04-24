#!/usr/bin/env python3
"""Local verification runner for caveman install surfaces."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CheckFailure(RuntimeError):
    pass


def section(title: str) -> None:
    print(f"\n== {title} ==")


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        args,
        cwd=cwd,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise CheckFailure(
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def read_json(path: Path) -> object:
    return json.loads(path.read_text())


def verify_synced_files() -> None:
    section("Synced Files")
    skill_source = ROOT / "skills/caveman/SKILL.md"
    rule_source = ROOT / "rules/caveman-activate.md"
    agent_source_dir = ROOT / "agents"
    generated_agent_dir = ROOT / ".github" / "agents"

    skill_copies = [
        ROOT / "caveman/SKILL.md",
        ROOT / "plugins/caveman/skills/caveman/SKILL.md",
        ROOT / ".cursor/skills/caveman/SKILL.md",
        ROOT / ".windsurf/skills/caveman/SKILL.md",
    ]
    for copy in skill_copies:
        ensure(copy.read_text() == skill_source.read_text(), f"Skill copy mismatch: {copy}")

    rule_copies = [
        ROOT / ".clinerules/caveman.md",
        ROOT / ".github/copilot-instructions.md",
    ]
    for copy in rule_copies:
        ensure(copy.read_text() == rule_source.read_text(), f"Rule copy mismatch: {copy}")

    with zipfile.ZipFile(ROOT / "caveman.skill") as archive:
        ensure("caveman/SKILL.md" in archive.namelist(), "caveman.skill missing caveman/SKILL.md")
        ensure(
            archive.read("caveman/SKILL.md").decode("utf-8") == skill_source.read_text(),
            "caveman.skill payload mismatch",
        )

    source_agents = []
    if agent_source_dir.exists():
        source_agents = sorted(
            path
            for path in agent_source_dir.iterdir()
            if path.is_file() and path.name != ".gitkeep" and path.suffix == ".md"
        )

    if source_agents:
        for source in source_agents:
            generated = generated_agent_dir / source.name
            ensure(generated.exists(), f"Generated agent missing: {generated}")
            ensure(generated.read_text() == source.read_text(), f"Generated agent mismatch: {generated}")
    else:
        ensure((generated_agent_dir / ".gitkeep").exists(), ".github/agents missing .gitkeep")

    print("Synced copies and caveman.skill zip OK")


def verify_manifests_and_syntax() -> None:
    section("Manifests And Syntax")

    manifest_paths = [
        ROOT / ".agents/plugins/marketplace.json",
        ROOT / ".claude-plugin/plugin.json",
        ROOT / ".claude-plugin/marketplace.json",
        ROOT / ".codex/hooks.json",
        ROOT / "gemini-extension.json",
        ROOT / "plugins/caveman/.codex-plugin/plugin.json",
    ]
    for path in manifest_paths:
        read_json(path)

    run(["node", "--check", "hooks/caveman-config.js"])
    run(["node", "--check", "hooks/caveman-activate.js"])
    run(["node", "--check", "hooks/caveman-mode-tracker.js"])
    run(["bash", "-n", "hooks/install.sh"])
    run(["bash", "-n", "hooks/uninstall.sh"])
    run(["bash", "-n", "hooks/caveman-statusline.sh"])

    # Ensure install/uninstall scripts include caveman-config.js
    install_sh = (ROOT / "hooks/install.sh").read_text()
    uninstall_sh = (ROOT / "hooks/uninstall.sh").read_text()
    ensure("caveman-config.js" in install_sh, "install.sh missing caveman-config.js")
    ensure("caveman-config.js" in uninstall_sh, "uninstall.sh missing caveman-config.js")

    print("JSON manifests and JS/bash syntax OK")


def verify_powershell_static() -> None:
    section("PowerShell Static Checks")
    install_text = (ROOT / "hooks/install.ps1").read_text()
    uninstall_text = (ROOT / "hooks/uninstall.ps1").read_text()
    statusline_text = (ROOT / "hooks/caveman-statusline.ps1").read_text()

    ensure("caveman-config.js" in install_text, "install.ps1 missing caveman-config.js")
    ensure("caveman-config.js" in uninstall_text, "uninstall.ps1 missing caveman-config.js")
    ensure("caveman-statusline.ps1" in install_text, "install.ps1 missing statusline.ps1")
    ensure("caveman-statusline.ps1" in uninstall_text, "uninstall.ps1 missing statusline.ps1")
    ensure("-AsHashtable" not in install_text, "install.ps1 should stay compatible with Windows PowerShell 5.1")
    ensure(
        "powershell -ExecutionPolicy Bypass -File" in install_text,
        "install.ps1 missing PowerShell statusline command",
    )
    ensure("[CAVEMAN" in statusline_text, "caveman-statusline.ps1 missing badge output")

    print("Windows install path statically wired")


def load_compress_modules():
    sys.path.insert(0, str(ROOT / "caveman-compress"))
    import scripts.benchmark  # noqa: F401
    import scripts.cli as cli
    import scripts.compress  # noqa: F401
    import scripts.detect as detect
    import scripts.targets as targets
    import scripts.validate as validate

    return cli, detect, validate, targets


def verify_compress_fixtures() -> None:
    section("Compress Fixtures")
    _, detect, validate, _ = load_compress_modules()

    fixtures = sorted((ROOT / "tests/caveman-compress").glob("*.original.md"))
    ensure(fixtures, "No caveman-compress fixtures found")

    for original in fixtures:
        compressed = original.with_name(original.name.replace(".original.md", ".md"))
        ensure(compressed.exists(), f"Missing compressed fixture for {original.name}")
        result = validate.validate(original, compressed)
        ensure(result.is_valid, f"Fixture validation failed for {compressed.name}: {result.errors}")
        ensure(detect.should_compress(compressed), f"Fixture should be compressible: {compressed.name}")

    print(f"Validated {len(fixtures)} caveman-compress fixture pairs")


def verify_compress_target_resolution() -> None:
    section("Compress Target Resolution")
    _, _, _, targets = load_compress_modules()

    with tempfile.TemporaryDirectory(prefix="caveman-compress-targets-") as temp_root:
        root = Path(temp_root)
        docs_dir = root / "docs"
        docs_dir.mkdir()

        claude = root / "CLAUDE.md"
        gemini = root / "GEMINI.md"
        prefs = docs_dir / "preferences.md"

        claude.write_text("# Claude\n")
        gemini.write_text("# Gemini\n")
        prefs.write_text("# Prefs\n")

        resolution = targets.resolve_targets([str(claude)], cwd=root)
        ensure(resolution.files == [claude.resolve()], "single target resolution failed")
        ensure(not resolution.unmatched, "single target should not leave unmatched entries")

        resolution = targets.resolve_targets(['["CLAUDE.md", "GEMINI.md"]'], cwd=root)
        ensure(
            resolution.files == [claude.resolve(), gemini.resolve()],
            "list target resolution failed",
        )
        ensure(not resolution.unmatched, "list target should not leave unmatched entries")

        resolution = targets.resolve_targets(["CLAUDE.md,GEMINI.md", "docs/**/*.md"], cwd=root)
        ensure(
            resolution.files == [claude.resolve(), gemini.resolve(), prefs.resolve()],
            "combined list + glob target resolution failed",
        )
        ensure(not resolution.unmatched, "glob target should not leave unmatched entries")

        resolution = targets.resolve_targets(["missing*.md"], cwd=root)
        ensure(not resolution.files, "missing glob should not resolve files")
        ensure(resolution.unmatched == ["missing*.md"], "missing glob should stay unmatched")

    print("Compress target resolution OK")


def verify_compress_backend_resolution() -> None:
    section("Compress Backend Resolution")

    sys.path.insert(0, str(ROOT / "caveman-compress"))
    import scripts.providers as providers

    env_keys = [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "CAVEMAN_MODEL",
        "CAVEMAN_PROVIDER",
    ]
    original_env = {key: os.environ.get(key) for key in env_keys}
    original_which = providers.shutil.which

    def clear_env() -> None:
        for key in env_keys:
            os.environ.pop(key, None)

    try:
        clear_env()
        os.environ["OPENAI_API_KEY"] = "test-openai"
        os.environ["CAVEMAN_MODEL"] = "gpt-5"
        backend = providers.resolve_backend()
        ensure(backend.provider == "openai", "gpt model should resolve to OpenAI backend")

        clear_env()
        os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
        backend = providers.resolve_backend()
        ensure(backend.provider == "anthropic", "Anthropic key should resolve to Anthropic backend")

        clear_env()
        providers.shutil.which = lambda command: "/usr/local/bin/claude" if command == "claude" else None
        backend = providers.resolve_backend()
        ensure(backend.provider == "anthropic", "Claude CLI should resolve to Anthropic backend")
        ensure(backend.label == "Claude CLI", "Claude CLI backend label mismatch")

        clear_env()
        os.environ["OPENAI_API_KEY"] = "test-openai"
        os.environ["CAVEMAN_PROVIDER"] = "openai"
        backend = providers.resolve_backend()
        ensure(backend.provider == "openai", "explicit OpenAI provider should be honored")

        clear_env()
        os.environ["OPENAI_API_KEY"] = "test-openai"
        os.environ["CAVEMAN_PROVIDER"] = "openai"
        os.environ["CAVEMAN_MODEL"] = "claude-sonnet-4-5"
        try:
            providers.resolve_backend()
        except RuntimeError as exc:
            ensure("conflicts with provider" in str(exc), "provider/model conflict error mismatch")
        else:
            raise CheckFailure("provider/model conflict should raise RuntimeError")
    finally:
        providers.shutil.which = original_which
        clear_env()
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value

    print("Compress backend resolution OK")


def verify_compress_cli() -> None:
    section("Compress CLI")

    skip_result = run(
        ["python3", "-m", "scripts", "../hooks/install.sh"],
        cwd=ROOT / "caveman-compress",
        check=False,
    )
    ensure(skip_result.returncode == 0, "compress CLI skip path should exit 0")
    ensure("Detected: code" in skip_result.stdout, "compress CLI skip path missing detection output")
    ensure(
        "Skipping: file is not natural language" in skip_result.stdout,
        "compress CLI skip path missing skip output",
    )

    missing_result = run(
        ["python3", "-m", "scripts", "../does-not-exist.md"],
        cwd=ROOT / "caveman-compress",
        check=False,
    )
    ensure(missing_result.returncode == 1, "compress CLI missing-file path should exit 1")
    ensure("No files matched" in missing_result.stdout, "compress CLI missing-file output mismatch")

    pattern_result = run(
        ["python3", "-m", "scripts", "../hooks/*.sh"],
        cwd=ROOT / "caveman-compress",
        check=False,
    )
    ensure(pattern_result.returncode == 0, "compress CLI glob path should exit 0")
    ensure("Resolved 3 file(s)" in pattern_result.stdout, "compress CLI glob path missing resolution output")
    ensure("Summary: success=0 skipped=3 failed=0 unmatched=0" in pattern_result.stdout, "compress CLI glob summary mismatch")

    list_result = run(
        ["python3", "-m", "scripts", '["../hooks/install.sh", "../hooks/uninstall.sh"]'],
        cwd=ROOT / "caveman-compress",
        check=False,
    )
    ensure(list_result.returncode == 0, "compress CLI list path should exit 0")
    ensure("Resolved 2 file(s)" in list_result.stdout, "compress CLI list path missing resolution output")
    ensure("Summary: success=0 skipped=2 failed=0 unmatched=0" in list_result.stdout, "compress CLI list summary mismatch")

    partial_result = run(
        ["python3", "-m", "scripts", "../hooks/install.sh", "../missing*.md"],
        cwd=ROOT / "caveman-compress",
        check=False,
    )
    ensure(partial_result.returncode == 2, "compress CLI partial miss path should exit 2")
    ensure("No files matched" in partial_result.stdout, "compress CLI partial miss missing unmatched output")
    ensure("Summary: success=0 skipped=1 failed=0 unmatched=1" in partial_result.stdout, "compress CLI partial miss summary mismatch")

    print("Compress CLI skip/error paths OK")


def verify_hook_install_flow() -> None:
    section("Claude Hook Flow")

    ensure(shutil.which("node") is not None, "node is required for hook verification")
    ensure(shutil.which("bash") is not None, "bash is required for hook verification")

    with tempfile.TemporaryDirectory(prefix="caveman-verify-") as temp_root:
        temp_root_path = Path(temp_root)
        home = temp_root_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)

        existing_settings = {
            "statusLine": {"type": "command", "command": "bash /tmp/existing-statusline.sh"},
            "hooks": {"Notification": [{"hooks": [{"type": "command", "command": "echo keep-me"}]}]},
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing_settings, indent=2) + "\n")

        run(["bash", "hooks/install.sh"], env={"HOME": str(home)})

        settings = read_json(claude_dir / "settings.json")
        hooks = settings["hooks"]
        ensure(settings["statusLine"]["command"] == "bash /tmp/existing-statusline.sh", "install.sh clobbered existing statusLine")
        ensure("SessionStart" in hooks, "SessionStart hook missing after install")
        ensure("UserPromptSubmit" in hooks, "UserPromptSubmit hook missing after install")

        activate = run(
            ["node", "hooks/caveman-activate.js"],
            env={"HOME": str(home)},
        )
        ensure("CAVEMAN MODE ACTIVE." in activate.stdout, "activation output missing caveman banner")
        ensure("STATUSLINE SETUP NEEDED" not in activate.stdout, "activation should stay quiet when custom statusline exists")
        ensure((claude_dir / ".caveman-active").read_text() == "full", "activation flag should default to full")

        # Test configurable default mode via CAVEMAN_DEFAULT_MODE env var
        activate_custom = run(
            ["node", "hooks/caveman-activate.js"],
            env={"HOME": str(home), "CAVEMAN_DEFAULT_MODE": "ultra"},
        )
        ensure("CAVEMAN MODE ACTIVE." in activate_custom.stdout, "activation with custom default missing banner")
        ensure((claude_dir / ".caveman-active").read_text() == "ultra", "CAVEMAN_DEFAULT_MODE=ultra should set flag to ultra")
        # Test "off" mode — activation skipped, flag removed
        activate_off = run(
            ["node", "hooks/caveman-activate.js"],
            env={"HOME": str(home), "CAVEMAN_DEFAULT_MODE": "off"},
        )
        ensure("CAVEMAN MODE ACTIVE." not in activate_off.stdout, "off mode should not emit caveman banner")
        ensure(not (claude_dir / ".caveman-active").exists(), "off mode should remove flag file")

        # Test mode tracker with /caveman when default is off — should NOT write flag
        subprocess.run(
            ["node", "hooks/caveman-mode-tracker.js"],
            cwd=ROOT,
            env={**os.environ, "HOME": str(home), "CAVEMAN_DEFAULT_MODE": "off"},
            text=True,
            input='{"prompt":"/caveman"}',
            capture_output=True,
            check=True,
        )
        ensure(not (claude_dir / ".caveman-active").exists(), "/caveman with off default should not write flag")

        # Reset back to full for subsequent tests
        (claude_dir / ".caveman-active").write_text("full")

        run(
            ["node", "hooks/caveman-mode-tracker.js"],
            env={"HOME": str(home)},
            check=True,
        )

        ultra_prompt = subprocess.run(
            ["node", "hooks/caveman-mode-tracker.js"],
            cwd=ROOT,
            env={**os.environ, "HOME": str(home)},
            text=True,
            input='{"prompt":"/caveman ultra"}',
            capture_output=True,
            check=True,
        )
        ensure(ultra_prompt.stdout == "", "mode tracker should stay silent")
        ensure((claude_dir / ".caveman-active").read_text() == "ultra", "mode tracker did not record ultra")

        subprocess.run(
            ["node", "hooks/caveman-mode-tracker.js"],
            cwd=ROOT,
            env={**os.environ, "HOME": str(home)},
            text=True,
            input='{"prompt":"normal mode"}',
            capture_output=True,
            check=True,
        )
        ensure(not (claude_dir / ".caveman-active").exists(), "normal mode should remove flag file")

        (claude_dir / ".caveman-active").write_text("wenyan-ultra")
        statusline = run(
            ["bash", "hooks/caveman-statusline.sh"],
            env={"HOME": str(home)},
        )
        ensure("[CAVEMAN:WENYAN-ULTRA]" in statusline.stdout, "statusline badge output mismatch")

        reinstall = run(["bash", "hooks/install.sh"], env={"HOME": str(home)})
        ensure("Nothing to do" in reinstall.stdout, "install.sh should be idempotent")

        run(["bash", "hooks/uninstall.sh"], env={"HOME": str(home)})
        settings_after = read_json(claude_dir / "settings.json")
        ensure(settings_after == existing_settings, "uninstall.sh did not restore non-caveman settings")
        ensure(not (claude_dir / ".caveman-active").exists(), "uninstall.sh should remove flag file")

    with tempfile.TemporaryDirectory(prefix="caveman-verify-fresh-") as temp_root:
        home = Path(temp_root) / "home"
        run(["bash", "hooks/install.sh"], env={"HOME": str(home)})
        claude_dir = home / ".claude"
        settings = read_json(claude_dir / "settings.json")
        ensure("statusLine" in settings, "fresh install should configure statusline")
        activate = run(["node", "hooks/caveman-activate.js"], env={"HOME": str(home)})
        ensure("STATUSLINE SETUP NEEDED" not in activate.stdout, "fresh install should not nudge for statusline")
        run(["bash", "hooks/uninstall.sh"], env={"HOME": str(home)})
        ensure(read_json(claude_dir / "settings.json") == {}, "fresh uninstall should leave empty settings")

    print("Claude hook install/uninstall flow OK")


def main() -> int:
    checks = [
        verify_synced_files,
        verify_manifests_and_syntax,
        verify_powershell_static,
        verify_compress_fixtures,
        verify_compress_target_resolution,
        verify_compress_backend_resolution,
        verify_compress_cli,
        verify_hook_install_flow,
    ]

    try:
        for check in checks:
            check()
    except CheckFailure as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1

    print("\nAll local verification checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
