#!/usr/bin/env python3
"""
astra-sre triage.py — Phase 2-⑤: Symptom → Incident Matcher
Search sre_incidents knowledge base for similar past incidents.

Usage:
    ./triage.py "E2EE 无法解密 消息"
    ./triage.py "Gateway sync error 离线" --top 3
    ./triage.py --list                # List all incidents
    ./triage.py --tag P1              # Filter by severity tag
"""
import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# ── DB config ────────────────────────────────────────────────
DB_CONFIG = {
    "host": os.environ.get("ASTRA_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("ASTRA_DB_PORT", "5432")),
    "dbname": os.environ.get("ASTRA_DB_NAME", "astra_kb"),
    "user": os.environ.get("ASTRA_DB_USER", "astramcp"),
    "password": os.environ.get("ASTRA_DB_PASSWORD", "astra_kb_2026"),
}

INCIDENTS_KB = "sre_incidents"


# ── Data ─────────────────────────────────────────────────────
@dataclass
class Match:
    kb: str
    title: str
    content: str
    score: float
    source: Optional[str]
    tags: list[str]

    @property
    def severity(self) -> str:
        """Extract severity from tags (handles comma-joined strings)."""
        all_tags = []
        for t in self.tags:
            if isinstance(t, str):
                all_tags.extend([tag.strip().lower() for tag in t.split(",")])
            else:
                all_tags.append(str(t).strip().lower())
        for t in all_tags:
            if t in ("p1", "p2", "p3", "p0"):
                return t.upper()
        return "N/A"

    def snippet(self, max_len: int = 300) -> str:
        txt = self.content.replace("\n", " ").strip()
        return txt[:max_len] + ("…" if len(txt) > max_len else "")

    def summary(self) -> str:
        sev_emoji = {"P1": "🔴", "P2": "🟠", "P3": "🟡"}.get(self.severity, "⚪")
        return (
            f"{sev_emoji} [{self.severity}] {self.title}\n"
            f"   Score: {self.score:.3f}  |  Tags: {', '.join(self.tags[:5])}\n"
            f"   {self.snippet(200)}\n"
        )


# ── FTS search ───────────────────────────────────────────────
def build_tsquery(query: str) -> str:
    tokens = []
    for word in query.replace("'", "''").split():
        word = word.strip().lower()
        if len(word) > 1:
            tokens.append(f"{word}:*")
    return " & ".join(tokens) if tokens else "%"


def search_fts(kb_name: str, query: str, limit: int = 5) -> list[Match]:
    """Search a single KB using PostgreSQL full-text search."""
    import psycopg2

    tsquery = build_tsquery(query)
    if not tsquery or tsquery == "%":
        return []

    safe = kb_name.replace(" ", "_").lower()
    sql = f"""
        SELECT
            ts_rank(chunks.search_vec, to_tsquery('simple', %s), 32) AS score,
            ts_headline('simple', chunks.content, to_tsquery('simple', %s),
                        'MaxWords=50, MinWords=20') AS headline,
            chunks.id, chunks.title, chunks.content, chunks.source, chunks.tags
        FROM kb_{safe}.chunks
        WHERE chunks.search_vec @@ to_tsquery('simple', %s)
        ORDER BY score DESC
        LIMIT %s
    """

    results = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(sql, (tsquery, tsquery, tsquery, limit))
            for row in cur.fetchall():
                results.append(Match(
                    kb=kb_name,
                    title=row[3] or "",
                    content=row[4] or "",
                    score=round(float(row[0]), 4),
                    source=row[5],
                    tags=list(row[6]) if row[6] else [],
                ))
        conn.close()
    except Exception as e:
        print(f"❌ DB 查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    return results


def list_all(kb_name: str) -> list[Match]:
    """List all incidents in a KB (no ranking)."""
    import psycopg2

    safe = kb_name.replace(" ", "_").lower()
    sql = f"""
        SELECT DISTINCT ON (chunks.title)
            chunks.id, chunks.title, chunks.content, chunks.source, chunks.tags
        FROM kb_{safe}.chunks
        ORDER BY chunks.title, chunks.id
    """

    results = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                results.append(Match(
                    kb=kb_name,
                    title=row[1] or "",
                    content=row[2] or "",
                    score=1.0,
                    source=row[3],
                    tags=list(row[4]) if row[4] else [],
                ))
        conn.close()
    except Exception as e:
        print(f"❌ DB 查询失败: {e}", file=sys.stderr)
        sys.exit(1)

    return results


# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🔍 astra-sre triage — 诊断时自动搜 sre_incidents 找相似案例",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s \"E2EE 无法解密\"\n"
               "  %(prog)s \"Gateway sync error\" --top 5\n"
               "  %(prog)s --list\n"
               "  %(prog)s --tag P1",
    )
    parser.add_argument("query", nargs="?", help="症状描述（自然语言）")
    parser.add_argument("--top", type=int, default=5, help="最多返回几条 (default: 5)")
    parser.add_argument("--list", action="store_true", help="列出所有已记录的事故")
    parser.add_argument("--tag", help="按严重度标签过滤 (P1/P2/P3)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    # ── List mode ──
    if args.list:
        incidents = list_all(INCIDENTS_KB)
        if not incidents:
            print("📭 sre_incidents 知识库为空")
            return

        # Deduplicate by title
        seen = set()
        unique = []
        for inc in incidents:
            if inc.title not in seen:
                seen.add(inc.title)
                unique.append(inc)

        if args.tag:
            tag_filter = args.tag.upper()
            unique = [i for i in unique if tag_filter in [t.upper().strip() for t in i.tags]]

        print(f"\n📚 sre_incidents — {len(unique)} 条事故记录\n")
        for i, inc in enumerate(unique, 1):
            tags_str = ", ".join(inc.tags)
            print(f"  {i}. {inc.severity} {inc.title}")
            print(f"     Tags: {tags_str}")
            print()

        return

    # ── Search mode ──
    if not args.query:
        parser.print_help()
        sys.exit(1)

    matches = search_fts(INCIDENTS_KB, args.query, args.top)

    if args.tag:
        tag_filter = args.tag.upper()
        matches = [m for m in matches if tag_filter in [t.upper().strip() for t in m.tags]]

    if args.json:
        import json
        print(json.dumps([
            {
                "title": m.title,
                "score": m.score,
                "severity": m.severity,
                "tags": m.tags,
                "snippet": m.snippet(300),
                "full_content": m.content,
            }
            for m in matches
        ], ensure_ascii=False, indent=2))
        return

    # Markdown output (for agent consumption or human reading)
    if not matches:
        print(f"\n🔍 未在 sre_incidents 中找到与「{args.query}」匹配的案例\n")
        return

    print(f"\n🔍 搜索「{args.query}」— 找到 {len(matches)} 个匹配案例\n")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    for i, m in enumerate(matches, 1):
        print(f"### {i}. {m.severity} {m.title}")
        print(f"**相似度**: {m.score:.3f}")
        print(f"**标签**: {', '.join(m.tags)}")
        print(f"**摘要**: {m.snippet(200)}")
        print()

    print(f"ℹ️  完整 incident 内容可通过 kb_search('sre_incidents', '{args.query}') 获取\n")


if __name__ == "__main__":
    main()
