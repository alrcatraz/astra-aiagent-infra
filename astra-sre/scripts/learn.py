#!/usr/bin/env python3
"""
astra-sre learn.py — Phase 4: "两次原则"自动检测重复问题

Scans sre_incidents for problem patterns that have occurred 2+ times,
checks if corresponding sub-skills exist, and suggests creating new ones.

Usage:
    ./learn.py                           # 默认报告模式
    ./learn.py --json                    # JSON 输出
    ./learn.py --suggest                 # 输出可执行的 sub-skill 模板建议
    ./learn.py --cron                    # cron 友好模式（只在有新建议时输出）
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# ── DB config ────────────────────────────────────────────────
DB_CONFIG = {
    "host": os.environ.get("ASTRA_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("ASTRA_DB_PORT", "5432")),
    "dbname": os.environ.get("ASTRA_DB_NAME", "astra_kb"),
    "user": os.environ.get("ASTRA_DB_USER", "astramcp"),
    "password": os.environ.get("ASTRA_DB_PASSWORD", "astra_kb_2026"),
}

SKILLS_DIR = os.path.expanduser("~/.hermes/skills/sre")


# ── Data ─────────────────────────────────────────────────────
@dataclass
class Incident:
    title: str
    tags: list[str]
    severity: str = "N/A"

    def __post_init__(self):
        # Extract severity from tags
        for t in self.tags:
            clean_t = t.strip().lower()
            if clean_t in ("p0", "p1", "p2", "p3"):
                self.severity = clean_t.upper()
                break

    @property
    def tag_clusters(self) -> list[str]:
        """Extract meaningful tag clusters (non-severity, non-generic)."""
        skip = {"p0", "p1", "p2", "p3", "e2ee", "gateway", "crypto"}
        clusters = set()
        for t in self.tags:
            t = t.strip().lower()
            # Handle comma-joined tags
            for part in t.split(","):
                part = part.strip()
                if part and part not in skip and len(part) > 2:
                    clusters.add(part)
        return sorted(clusters)


def fetch_incidents() -> list[Incident]:
    """Fetch all incidents from sre_incidents chunks."""
    import psycopg2

    sql = """
        SELECT DISTINCT ON (chunks.title)
            chunks.title, chunks.tags
        FROM kb_sre_incidents.chunks
        ORDER BY chunks.title, chunks.id
    """

    incidents = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                tags = list(row[1]) if row[1] else []
                incidents.append(Incident(title=row[0] or "", tags=tags))
        conn.close()
    except Exception as e:
        print(f"❌ DB 查询失败: {e}", file=sys.stderr)
        sys.exit(1)
    return incidents


def get_existing_skills() -> list[str]:
    """List existing astra-sre-fix-* sub-skills."""
    if not os.path.isdir(SKILLS_DIR):
        return []
    skills = []
    for d in os.listdir(SKILLS_DIR):
        if d.startswith("astra-sre-fix-") or d.startswith("astra-sre-restart-"):
            skills.append(d)
    return skills


def suggest_skill_name(tag_cluster: str, incidents: list[Incident]) -> str:
    """Suggest a sub-skill name based on tag cluster and incidents."""
    # Clean up the tag for use in a skill name
    name = tag_cluster.lower().replace(" ", "-").replace("_", "-")
    name = re.sub(r'[^a-z0-9-]', '', name)
    name = re.sub(r'-+', '-', name).strip('-')

    if not name or len(name) < 3:
        name = f"issue-{incidents[0].title.split()[0].lower()[:10]}"

    return f"astra-sre-fix-{name[:30]}"


def generate_skill_template(skill_name: str, tag: str, incidents: list[Incident]) -> str:
    """Generate a SKILL.md template for a new sub-skill."""
    sev = max((i.severity for i in incidents), key=lambda x: {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(x, 99))
    sev_guide = {"P1": "L2/L3", "P2": "L2", "P3": "L1/L2"}.get(sev, "L2")

    refs = "\n".join(f"  - {i.title}" for i in incidents)

    return f"""---
name: {skill_name}
description: "自动生成的修复子 skill — 基于 sre_incidents 中 {len(incidents)} 条 '{tag}' 相关记录"
version: 0.1.0
author: ANGELIA (auto-generated)
platforms: [linux]
level: {sev_guide}
related_skills:
  - astra-sre-restart-service
---

# {skill_name}

> ⚡ 由 learn.py 自动生成的 sub-skill 模板（未经验证）
> 基于以下事故记录提炼：
{refs}

---

## 触发条件

<!-- 从事故记录中的"根因分析"部分提取 -->

## 诊断流程

<!-- 从事故记录中的"诊断"部分提取 -->

## 修复步骤

<!-- 从事故记录中的"修复方案"提取 -->
<!-- 标记每一步为 [auto] 或 [gate] -->

## 验证

<!-- 修复后如何验证 -->

## 已知陷阱

<!-- 从事故记录中的"经验教训"提取 -->
"""


# ── Analysis ─────────────────────────────────────────────────
def analyze(incidents: list[Incident], existing_skills: list[str]) -> dict:
    """Analyze incidents for repeat patterns."""
    # Group incidents by individual tags
    tag_groups = defaultdict(list)
    for inc in incidents:
        clusters = inc.tag_clusters
        # Also group by major topic keywords from title
        title_keywords = set()
        for kw in ["e2ee", "vps", "mcp", "ssh", "nas", "megolm", "gateway", "password",
                    "内存", "冗余", "假阳性", "密钥", "升配", "重启"]:
            if kw.lower() in inc.title.lower():
                title_keywords.add(kw)
        for kw in title_keywords:
            # Also map title keywords through canonical names
            kw_canonical = kw
            if kw in ("vps", "升配", "升级"):
                kw_canonical = "vps-recovery"
            tag_groups[kw_canonical].append(inc)

        for c in clusters:
            # Map related tags to canonical names
            canonical = c
            if c in ("stale-otk", "megolm", "shared-once", "reconnection", "双客户端冲突"):
                canonical = "e2ee"
            elif c in ("健康检查", "healthcheck", "time-mcp", "假阳性"):
                canonical = "healthcheck"
            elif c in ("升配", "升级", "vps"):
                canonical = "vps-recovery"
            elif c in ("密码", "密码过期"):
                canonical = "credential"
            elif c in ("内存", "冗余"):
                canonical = "resource-cleanup"
            tag_groups[canonical].append(inc)

    # Deduplicate within groups
    deduped = {}
    for tag, incs in tag_groups.items():
        seen = set()
        unique = []
        for i in incs:
            if i.title not in seen:
                seen.add(i.title)
                unique.append(i)
        if len(unique) >= 2:
            deduped[tag] = unique

    # Check if skill exists
    results = []
    for tag, incs in sorted(deduped.items()):
        suggested_name = suggest_skill_name(tag, incs)
        matched_skills = [s for s in existing_skills if tag.replace("-", "") in s.replace("_", "").replace("-", "")]
        has_skill = len(matched_skills) > 0

        results.append({
            "tag": tag,
            "count": len(incs),
            "severity": max((i.severity for i in incs), key=lambda x: {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(x, 99)),
            "incidents": [i.title for i in incs],
            "has_skill": has_skill,
            "existing_skills": matched_skills if has_skill else [],
            "suggested_skill": suggested_name if not has_skill else None,
            "template": generate_skill_template(suggested_name, tag, incs) if not has_skill else None,
        })

    return results


# ── Formatters ───────────────────────────────────────────────
def format_markdown(results: list[dict]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not results:
        print(f"\n✅ **两次原则扫描 · {now}** — 无重复模式，无需新子 skill\n")
        return

    print(f"\n📋 **两次原则扫描报告 · {now}**\n")
    print(f"发现 {len(results)} 个重复模式\n")

    for r in results:
        sev_emoji = {"P1": "🔴", "P2": "🟠", "P3": "🟡"}.get(r["severity"], "⚪")
        icon = "✅" if r["has_skill"] else "❌"
        print(f"### {icon} {sev_emoji} {r['tag']} — 出现 {r['count']} 次")
        for inc in r["incidents"]:
            print(f"  · {inc}")
        if r["has_skill"]:
            print(f"  ✅ 已有 sub-skill: {', '.join(r['existing_skills'])}")
        else:
            print(f"  ❌ 无 sub-skill")
            print(f"  💡 建议创建: `{r['suggested_skill']}`")
        print()

    # Summary of suggestions
    suggestions = [r for r in results if not r["has_skill"]]
    if suggestions:
        print("---\n### 🆕 建议新建的子 skill\n")
        for s in suggestions:
            print(f"**{s['suggested_skill']}** — 基于 {s['tag']} ({s['count']} 条记录)")
            print()
            if s["template"]:
                # Show first 5 lines of template
                preview = "\n".join(s["template"].split("\n")[1:8])
                print(f"```\n{preview}\n...\n```")
                print()

    print(f"ℹ️  扫描完成 · {now}\n")


def format_json(results: list[dict]):
    print(json.dumps(results, ensure_ascii=False, indent=2))


# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🧠 astra-sre learn — 两次原则自动检测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s              # 默认报告\n"
               "  %(prog)s --json       # JSON 输出\n"
               "  %(prog)s --suggest    # 输出模板\n"
               "  %(prog)s --cron       # 只在新建议时输出",
    )
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--suggest", action="store_true", help="输出可执行的 sub-skill 模板")
    parser.add_argument("--cron", action="store_true",
                        help="cron 友好模式：只有在有新建议时才输出，否则静默")

    args = parser.parse_args()

    incidents = fetch_incidents()
    existing_skills = get_existing_skills()
    results = analyze(incidents, existing_skills)

    # Filter to only suggestions if --suggest
    if args.suggest:
        results = [r for r in results if not r["has_skill"]]

    # Cron mode: only output if there are new suggestions
    if args.cron:
        new_suggestions = [r for r in results if not r["has_skill"]]
        if not new_suggestions:
            sys.exit(0)

    if args.json:
        format_json(results)
    else:
        format_markdown(results)

    # Exit code: 2 if there are unaddressed patterns
    unaddressed = sum(1 for r in results if not r["has_skill"])
    if unaddressed > 0 and not args.cron:
        sys.exit(2)


if __name__ == "__main__":
    main()
