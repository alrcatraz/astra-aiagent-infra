#!/usr/bin/env python3
"""
astra-lifecycle-sync — Ecosystem lifecycle hook sync tool.

Reads registry.yaml, evaluates lifecycle hooks declared by each component,
and synchronises the dynamic checklist sections in target SKILL.md files.

Usage:
  astra-lifecycle-sync              # Update mode (default)
  astra-lifecycle-sync --update     # Same as default
  astra-lifecycle-sync --check      # Dry-run: report differences, exit 1 if dirty
  astra-lifecycle-sync --install-hook  # Install git pre-commit hook in meta-repo
"""

import argparse
import os
import re
import stat
import sys
from pathlib import Path

import yaml


# ── Paths ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
META_DIR = SCRIPT_DIR.parent                 # astra-aiagent-infra/
PROJECTS_DIR = META_DIR.parent               # ~/Projects/astra/
PRIVATE_DIR = Path.home() / ".astra" / "repos" / "astra-aiagent-infra"

REGISTRY_PATH = META_DIR / "registry.yaml"   # authoritative source (dev)
HOOKS_DIR = PRIVATE_DIR                      # hook injection target (private)
# Map lifecycle type → target skill path (relative to HOOKS_DIR)
TARGET_SKILLS = {
    "closure":  "work-principles/skills/work-closure-check",
    "deploy":   "work-principles/skills/deploy-register",
}

MARKER_BEGIN = "<!-- LIFECYCLE_HOOKS_BEGIN -->"
MARKER_END   = "<!-- LIFECYCLE_HOOKS_END -->"

SEVERITY_ICONS = {
    "required":    "🔴",
    "recommended": "🟡",
    "optional":    "🔵",
}


# ── Helpers ────────────────────────────────────────────────

def load_registry(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_skill_path(lifecycle_type: str) -> Path:
    """Resolve the target SKILL.md for a given lifecycle type."""
    skill_path = TARGET_SKILLS[lifecycle_type]
    return HOOKS_DIR / skill_path / "SKILL.md"


def type_label(t: str) -> str:
    return {"closure": "Closure", "deploy": "Deploy"}.get(t, t.capitalize())


# ── Block generation ───────────────────────────────────────

def _generate_hook_items(component: dict, lifecycle_type: str) -> str:
    """Generate markdown checklist items for one component's lifecycle hooks."""
    name = component["name"]
    hooks = component.get("lifecycle", {}).get(lifecycle_type, [])
    if not hooks:
        return ""

    lines = [f"### From {name}"]
    for hook in hooks:
        icon = SEVERITY_ICONS.get(hook["severity"], "⚪")
        lines.append(f"- [{icon}] {hook['check']}")
        lines.append(f"  *({hook['severity']}, trigger: {hook['trigger']})*")
        if "command" in hook:
            lines.append(f"  ```bash")
            lines.append(f"  {hook['command']}")
            lines.append(f"  ```")
        if "action" in hook:
            lines.append(f"  > Action: `{hook['action']}`")
    return "\n".join(lines) + "\n"


def build_lifecycle_block(registry: dict, lifecycle_type: str) -> str:
    """Build the complete lifecycle block (including markers) for a lifecycle type."""
    components = registry.get("components", [])
    sections = []
    for comp in components:
        if "lifecycle" in comp and lifecycle_type in comp["lifecycle"]:
            section = _generate_hook_items(comp, lifecycle_type)
            if section:
                sections.append(section)

    label = type_label(lifecycle_type)

    if not sections:
        # No hooks → write an empty marker block so --check does not complain.
        return (
            f"{MARKER_BEGIN}\n"
            f"No {label.lower()} lifecycle hooks registered.\n"
            f"{MARKER_END}"
        )

    block = f"{MARKER_BEGIN}\n"
    block += f"**{label} lifecycle hooks — auto-generated.** Do not edit manually.\n"
    block += f"Run `astra-lifecycle-sync --update` to refresh.\n\n"
    block += "\n".join(sections)
    block += f"\n{MARKER_END}\n"
    return block


# ── File operations ────────────────────────────────────────

def add_markers(content: str, block: str) -> str:
    """Insert lifecycle marker block into SKILL.md content that lacks them."""
    # Insert before the last section that is a heading, or at end.
    insert_at = None
    for section_marker in ["## Pitfalls", "## 坑", "## License", "## 许可证"]:
        pos = content.rfind(f"\n{section_marker}")
        if pos != -1 and (insert_at is None or pos > insert_at):
            insert_at = pos

    if insert_at is not None:
        return content[:insert_at] + "\n\n" + block + "\n" + content[insert_at:]
    else:
        return content + "\n\n" + block


def update_skill_file(skill_path: Path, lifecycle_type: str, registry: dict) -> bool:
    """Update one SKILL.md with lifecycle hooks. Returns True if changed."""
    if not skill_path.exists():
        print(f"⚠  SKILL.md not found: {skill_path}", file=sys.stderr)
        return False

    content = skill_path.read_text(encoding="utf-8")
    new_block = build_lifecycle_block(registry, lifecycle_type)

    if MARKER_BEGIN in content:
        pattern = re.compile(
            rf"{re.escape(MARKER_BEGIN)}.*?{re.escape(MARKER_END)}",
            re.DOTALL,
        )
        if pattern.search(content):
            new_content = pattern.sub(new_block.strip(), content)
        else:
            print(f"⚠  Marker found but pattern mismatch in {skill_path}", file=sys.stderr)
            return False
    else:
        new_content = add_markers(content, new_block)

    if new_content == content:
        return False

    skill_path.write_text(new_content, encoding="utf-8")
    return True


# ── Modes ──────────────────────────────────────────────────

def check_mode(registry: dict) -> bool:
    """Check mode: report all diffs without writing. Returns True if dirty."""
    dirty = False

    for lifecycle_type in ["closure", "deploy"]:
        skill_path = resolve_skill_path(lifecycle_type)
        label = type_label(lifecycle_type)

        if not skill_path.exists():
            print(f"✗ {label}: SKILL.md not found at {skill_path}")
            dirty = True
            continue

        content = skill_path.read_text(encoding="utf-8")
        expected_block = build_lifecycle_block(registry, lifecycle_type)

        if MARKER_BEGIN in content:
            pattern = re.compile(
                rf"{re.escape(MARKER_BEGIN)}.*?{re.escape(MARKER_END)}",
                re.DOTALL,
            )
            match = pattern.search(content)
            if match:
                current_block = match.group(0)
                status = "✓" if current_block == expected_block.strip() else "✗"
                if status == "✗":
                    dirty = True
                print(f"{status} {label}: {skill_path.parent.name}/SKILL.md "
                      f"({'up to date' if status == '✓' else 'OUT OF SYNC — run --update'})")
            else:
                print(f"✗ {label}: markers found but regex mismatch")
                dirty = True
        else:
            print(f"✗ {label}: no lifecycle markers in {skill_path.parent.name}/SKILL.md")
            dirty = True

    return dirty


def update_mode(registry: dict) -> bool:
    """Update mode: write lifecycle hooks. Returns True if any file changed."""
    changed = False

    for lifecycle_type in ["closure", "deploy"]:
        skill_path = resolve_skill_path(lifecycle_type)
        label = type_label(lifecycle_type)

        result = update_skill_file(skill_path, lifecycle_type, registry)
        if result:
            print(f"✓ Updated {label.lower()} hooks in {skill_path.parent.name}/SKILL.md")
            changed = True
        else:
            print(f"  {label}: {skill_path.parent.name}/SKILL.md unchanged")

    return changed


def install_hook_mode():
    """Install the git pre-commit hook in the meta-repo."""
    hook_path = META_DIR / ".git" / "hooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    hook_script = """#!/usr/bin/env bash
# Astra lifecycle sync — pre-commit hook
# Auto-generated by astra-lifecycle-sync --install-hook
set -e

cd "$(git rev-parse --show-toplevel)"

if [ -f lifecycle/astra-lifecycle-sync.py ]; then
    python3 lifecycle/astra-lifecycle-sync.py --check
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ SKILL.md lifecycle hooks are out of sync."
        echo "   Run: python3 lifecycle/astra-lifecycle-sync.py --update"
        echo "   Then git add the updated SKILL.md files and commit again."
        exit 1
    fi
fi
"""

    # Write hook
    hook_path.write_text(hook_script)
    # Make executable
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"✓ Pre-commit hook installed: {hook_path}")
    return True


# ── Main ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Astra lifecycle hook sync — synchronises ecosystem hooks into SKILL.md files.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Dry-run: report differences without writing. Exit 1 if dirty.",
    )
    parser.add_argument(
        "--update", action="store_true",
        help="Write lifecycle hooks to target SKILL.md files (default behaviour).",
    )
    parser.add_argument(
        "--install-hook", action="store_true",
        help="Install git pre-commit hook in the meta-repo.",
    )
    args = parser.parse_args()

    if args.install_hook:
        install_hook_mode()
        return

    registry = load_registry(REGISTRY_PATH)

    if args.check:
        dirty = check_mode(registry)
        sys.exit(1 if dirty else 0)
    else:
        changed = update_mode(registry)
        if not changed:
            print("All SKILL.md files are up to date.")


if __name__ == "__main__":
    main()
