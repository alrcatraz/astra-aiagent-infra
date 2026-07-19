#!/usr/bin/env python3
"""harness-skill-audit.py — Audit all installed skills for frontmatter compliance.

Checks:
  - Every devops skill has valid YAML frontmatter
  - Required fields present: name, description, tags (>=3), triggers (>=3)
  - Description length and quality
  - Recent activity (last modified date)
  - Potential merge candidates (similar descriptions)

Usage:
  python3 ~/.hermes/scripts/harness-skill-audit.py
"""

import json
import re
import yaml
import os
from datetime import datetime
from pathlib import Path

SKILL_DIRS = [
    Path.home() / ".hermes" / "skills" / "devops",
    Path.home() / ".hermes" / "skills" / "software-development",
    Path.home() / ".hermes" / "skills" / "autonomous-ai-agents",
    Path.home() / ".hermes" / "skills" / "networking",
    Path.home() / ".hermes" / "skills" / "sre",
    Path.home() / ".hermes" / "skills" / "vcs",
]
STALE_DAYS = 180  # skills untouched for 180 days are stale


def _parse_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """Extract YAML frontmatter from a SKILL.md file."""
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError):
        return None, "cannot read"

    # Check for frontmatter markers
    if not text.startswith("---"):
        return None, "no frontmatter (no leading ---)"

    # Find closing ---
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return None, "no closing --- in frontmatter"

    yaml_text = text[3:end_idx]
    try:
        fm = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"

    if not isinstance(fm, dict):
        return None, "frontmatter is not a dict"

    return fm, None


def _check_frontmatter(fm: dict, path: Path) -> list[str]:
    """Check a frontmatter dict for compliance. Returns list of issues."""
    issues = []

    # — Required top-level fields —
    for field in ("name", "description"):
        val = fm.get(field)
        if not val:
            issues.append(f"missing required field: {field}")

    # — metadata.hermes.tags —
    tags = fm.get("metadata", {}).get("hermes", {}).get("tags", [])
    if not tags:
        issues.append("missing metadata.hermes.tags")
    elif len(tags) < 3:
        issues.append(f"only {len(tags)} tags (need >=3): {tags}")

    # — triggers —
    triggers = fm.get("triggers", [])
    if not triggers:
        issues.append("missing triggers")
    elif len(triggers) < 3:
        issues.append(f"only {len(triggers)} triggers (need >=3): {triggers}")

    # — Description quality —
    desc = fm.get("description", "")
    if len(desc) < 20:
        issues.append(f"description too short ({len(desc)} chars)")
    if len(desc) > 500:
        issues.append(f"description very long ({len(desc)} chars)")

    return issues


def _stale_check(path: Path) -> bool:
    """Check if a SKILL.md hasn't been modified in STALE_DAYS."""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    delta = datetime.now() - mtime
    return delta.days > STALE_DAYS


def _find_merge_candidates(
    skills: list[dict],
) -> list[tuple[str, str, float]]:
    """Find skills with similar descriptions suggesting they might merge."""
    candidates = []
    for i, a in enumerate(skills):
        for j, b in enumerate(skills):
            if j <= i:
                continue
            ad = a.get("desc", "").lower()
            bd = b.get("desc", "").lower()
            # Simple overlap heuristic: share significant word overlap
            a_words = set(re.findall(r"\w{4,}", ad))
            b_words = set(re.findall(r"\w{4,}", bd))
            if not a_words or not b_words:
                continue
            overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
            if overlap > 0.5:
                candidates.append((a["name"], b["name"], round(overlap, 2)))
    return candidates


def audit() -> dict:
    """Run the full skill audit."""
    all_skills = []
    issues_list = []
    stale_list = []

    for skill_dir in SKILL_DIRS:
        if not skill_dir.exists():
            continue
        for entry in sorted(skill_dir.iterdir()):
            if not entry.is_dir():
                continue
            sk_path = entry / "SKILL.md"
            if not sk_path.exists():
                continue

            fm, err = _parse_frontmatter(sk_path)
            if err:
                issues_list.append({
                    "skill": entry.name,
                    "path": str(sk_path),
                    "issues": [err],
                })
                all_skills.append({"name": entry.name, "desc": ""})
                continue

            issues = _check_frontmatter(fm, sk_path)
            desc = fm.get("description", "")
            all_skills.append({"name": entry.name, "desc": desc})

            if issues:
                issues_list.append({
                    "skill": entry.name,
                    "path": str(sk_path),
                    "issues": issues,
                })

            if _stale_check(sk_path):
                stale_list.append({
                    "skill": entry.name,
                    "path": str(sk_path),
                    "last_modified": datetime.fromtimestamp(
                        os.path.getmtime(sk_path)
                    ).isoformat()[:10],
                })

    merge_candidates = _find_merge_candidates(all_skills)

    return {
        "total_skills": len(all_skills),
        "skills_with_issues": len(issues_list),
        "stale_skills": len(stale_list),
        "merge_candidates": len(merge_candidates),
        "issues": issues_list,
        "stale": stale_list,
        "merge_candidates": merge_candidates,
        "healthy_skills": len(all_skills) - len(issues_list),
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
