#!/usr/bin/env python3
"""
astra-sre diagnose.sh — Phase 2-⑥: 子代理并行排查框架

Runs multiple diagnostic probes in parallel and aggregates findings.
Intended to be called by the agent during incident response.

Usage:
    ./diagnose.py                          # 全量诊断（所有维度）
    ./diagnose.py --mode network           # 只查网络
    ./diagnose.py --mode e2ee              # 只查 E2EE
    ./diagnose.py --mode triage,gateway    # 查 triage + gateway
    ./diagnose.py --symptom "无法解密"      # 带症状描述
    ./diagnose.py --json                  # JSON 输出
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

HERMES_HOME = os.path.expanduser("~/.hermes")
SCRIPTS = os.path.join(HERMES_HOME, "scripts")
ASTRA_SRE = os.path.join(os.path.dirname(__file__), "..")
TRIAGE = os.path.join(os.path.dirname(__file__), "triage.py")

TIMEOUT = 15  # per-probe timeout


# ── Result model ─────────────────────────────────────────────
@dataclass
class ProbeResult:
    name: str
    status: str  # ok / warn / error
    summary: str
    details: str = ""
    recommendations: list[str] = field(default_factory=list)


# ── Probe definitions ────────────────────────────────────────
def probe_triage(symptom: str = "") -> ProbeResult:
    """Search sre_incidents for matching past incidents."""
    if not symptom:
        return ProbeResult("triage", "ok", "无症状，跳过 triage")

    try:
        r = subprocess.run(
            [sys.executable, TRIAGE, symptom, "--top", "3", "--json"],
            capture_output=True, text=True, timeout=TIMEOUT,
            env={**os.environ, "ASTRA_DB_PASSWORD": os.environ.get("ASTRA_DB_PASSWORD", "")},
        )
        if r.returncode != 0:
            return ProbeResult("triage", "error", f"triage 执行失败: {r.stderr[:200]}")

        matches = json.loads(r.stdout)
        if not matches:
            return ProbeResult("triage", "ok", f"「{symptom}」无匹配历史案例", details="sre_incidents 中未找到相似记录")

        lines = []
        recs = []
        for m in matches:
            lines.append(f"  {m['severity']} {m['title']} (score={m['score']:.3f})")
        return ProbeResult(
            "triage", "warn" if any(m["severity"] in ("P1", "P2") for m in matches) else "ok",
            f"找到 {len(matches)} 个匹配历史案例",
            details="\n".join(lines),
            recommendations=["参考历史案例的修复方案", f"kb_search('sre_incidents', '{symptom}')"],
        )
    except Exception as e:
        return ProbeResult("triage", "error", f"triage 异常: {e}")


def probe_gateway() -> ProbeResult:
    """Check Gateway process, logs, and E2EE state."""
    recs = []
    details = []

    # Process
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "hermes-gateway"],
        capture_output=True, text=True, timeout=5,
    )
    gw_status = r.stdout.strip()
    details.append(f"  Gateway: {gw_status}")

    if gw_status not in ("active", "activating"):
        return ProbeResult("gateway", "error", f"Gateway 不在运行 ({gw_status})", details="\n".join(details),
                          recommendations=["systemctl --user start hermes-gateway"])

    # Log tail — check for recent errors
    gw_log = os.path.join(HERMES_HOME, "logs", "gateway.log")
    if os.path.exists(gw_log):
        r = subprocess.run(
            ["tail", "-50", gw_log],
            capture_output=True, text=True, timeout=5,
        )
        log_tail = r.stdout
        errors = [l for l in log_tail.splitlines()
                  if any(kw in l.lower() for kw in ["error", "otk", "decrypt", "stale", "401"])]
        sync_errors = [l for l in log_tail.splitlines() if "sync error" in l.lower()]

        if sync_errors:
            details.append(f"  ⚠️ sync 错误: {len(sync_errors)} 次（最近 {sync_errors[-1][:80]}）")
            recs.append("检查 DNS/网络稳定性")
        if errors:
            details.append(f"  ⚠️ {len(errors)} 条错误日志")
            for e in errors[-3:]:
                details.append(f"    {e.strip()[:100]}")
        else:
            details.append("  ✅ 日志无错误")

        # Cross-signing
        if "cross-signing verified" in log_tail:
            details.append("  ✅ Cross-signing 已验证")
        elif "cross-signing verification failed" in log_tail or "recovery key verification failed" in log_tail:
            details.append("  ❌ Cross-signing 失败")
            recs.append("运行 full-e2ee-recovery Variant B")

    # E2EE crypto.db
    crypto_db = os.path.join(HERMES_HOME, "platforms", "matrix", "store", "crypto.db")
    if os.path.exists(crypto_db):
        size = os.path.getsize(crypto_db)
        details.append(f"  crypto.db: {size / 1024:.0f} KB")

    status = "error" if any("❌" in d for d in details) else \
             "warn" if any("⚠️" in d for d in details) else "ok"
    return ProbeResult("gateway", status, f"Gateway {gw_status}", details="\n".join(details),
                      recommendations=recs)


def probe_services() -> ProbeResult:
    """Check systemd service statuses."""
    services = ["hermes-gateway", "postgresql", "searxng-core"]
    details = []
    recs = []

    for svc in services:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", svc] if svc == "hermes-gateway"
            else ["systemctl", "is-active", svc],
            capture_output=True, text=True, timeout=5,
        )
        st = r.stdout.strip()
        icon = "✅" if st == "active" else "❌" if st in ("inactive", "failed") else "⚠️"
        details.append(f"  {icon} {svc}: {st}")
        if st in ("inactive", "failed"):
            recs.append(f"systemctl start {svc}")

    # MCP processes
    r = subprocess.run(["pgrep", "-af", "mcp-server"], capture_output=True, text=True, timeout=5)
    mcp_count = len([l for l in r.stdout.splitlines() if l.strip()])
    details.append(f"  ℹ️  MCP 进程数: {mcp_count}")

    status = "error" if any("❌" in d for d in details) else \
             "warn" if any("⚠️" in d for d in details) else "ok"
    return ProbeResult("services", status, f"{len(services)} 个服务检查", details="\n".join(details),
                      recommendations=recs)


def probe_network() -> ProbeResult:
    """Check connectivity to key endpoints."""
    endpoints = [
        ("SearXNG", "http://127.0.0.2:8931/search"),
        ("DeepSeek API", "https://api.deepseek.com"),
        ("HuggingFace", "https://router.huggingface.co"),
        ("Synapse", "http://localhost:8008"),
    ]
    details = []
    recs = []

    for name, url in endpoints:
        r = subprocess.run(
            ["curl", "-s", "--connect-timeout", "5", "-o", "/dev/null", "-w", "%{http_code}:%{time_total}s", url],
            capture_output=True, text=True, timeout=8,
        )
        out = r.stdout.strip()
        code = out.split(":")[0] if ":" in out else "000"
        icon = "✅" if code == "200" else "❌"
        details.append(f"  {icon} {name}: HTTP {code}")
        if code == "000":
            recs.append(f"{name} 不可达 — 检查网络/DNS/GFW")

    # DNS check
    r = subprocess.run(
        ["dig", "+short", "api.deepseek.com", "A"],
        capture_output=True, text=True, timeout=5,
    )
    if r.stdout.strip():
        details.append(f"  ✅ DNS (deepseek): {r.stdout.strip()[:40]}")
    else:
        details.append(f"  ⚠️ DNS 解析失败 (deepseek)")

    status = "error" if any("❌" in d for d in details) else \
             "warn" if any("⚠️" in d for d in details) else "ok"
    return ProbeResult("network", status, "网络连通性检查", details="\n".join(details),
                      recommendations=recs)


def probe_system() -> ProbeResult:
    """Check system resources."""
    details = []

    # Disk
    r = subprocess.run(
        "df / --output=pcent,target,size,avail | tail -1",
        shell=True, capture_output=True, text=True, timeout=5,
    )
    disk = r.stdout.strip()
    details.append(f"  💾 磁盘: {disk}")

    # Memory
    r = subprocess.run(
        "free -h | grep Mem",
        shell=True, capture_output=True, text=True, timeout=5,
    )
    mem = r.stdout.strip()
    details.append(f"  🧠 内存: {mem}")

    # Load & Uptime
    r = subprocess.run(
        "uptime",
        shell=True, capture_output=True, text=True, timeout=5,
    )
    details.append(f"  ⏱️  {r.stdout.strip()}")

    # Top memory processes
    r = subprocess.run(
        "ps aux --sort=-%mem | head -5 | awk '{print $11,$4\"%\"}'",
        shell=True, capture_output=True, text=True, timeout=5,
    )
    top = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    details.append(f"  🔝 内存 TOP5: {', '.join(top[:3])}")

    # Extract disk usage percentage for severity
    disk_pct = 0
    try:
        disk_pct = int(disk.split("%")[0].split()[-1])
    except (ValueError, IndexError):
        pass

    status = "error" if disk_pct > 92 else "warn" if disk_pct > 85 else "ok"
    recs = []
    if disk_pct > 85:
        recs.append(f"磁盘使用率 {disk_pct}%，建议清理")

    return ProbeResult("system", status, f"系统资源 (磁盘 {disk_pct}%)", details="\n".join(details),
                      recommendations=recs)


# ── All probes registry ──────────────────────────────────────
PROBES = {
    "triage": probe_triage,
    "gateway": probe_gateway,
    "services": probe_services,
    "network": probe_network,
    "system": probe_system,
}

SHORT_NAMES = {
    "t": "triage",
    "g": "gateway",
    "s": "services",
    "n": "network",
    "sys": "system",
}


# ── Formatters ───────────────────────────────────────────────
def format_markdown(results: list[ProbeResult], symptom: str, elapsed: float):
    stable = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🔍 **astra-sre 诊断报告 · {stable}**")
    if symptom:
        print(f"   症状: {symptom}")
    print(f"   耗时: {elapsed:.1f}s")
    print()

    # Summary line
    ok_count = sum(1 for r in results if r.status == "ok")
    warn_count = sum(1 for r in results if r.status == "warn")
    err_count = sum(1 for r in results if r.status == "error")
    icons = []
    if ok_count:
        icons.append(f"✅ {ok_count}")
    if warn_count:
        icons.append(f"⚠️ {warn_count}")
    if err_count:
        icons.append(f"❌ {err_count}")
    status_icon = "✅" if err_count == 0 and warn_count == 0 else \
                  "⚠️" if err_count == 0 else "❌"
    print(f"{status_icon} **概览**: {' · '.join(icons)} 个维度\n")

    # Detail per probe
    for r in results:
        sev_icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}.get(r.status, "ℹ️")
        print(f"### {sev_icon} {r.name}")
        print(f"  {r.summary}")
        if r.details:
            print(f"{r.details}")
        if r.recommendations:
            print(f"  💡 **建议:**")
            for rec in r.recommendations:
                print(f"    · {rec}")
        print()

    # Action items
    all_recs = [rec for r in results for rec in r.recommendations]
    if all_recs:
        print("---\n### 🎯 行动项\n")
        for i, rec in enumerate(all_recs, 1):
            print(f"  {i}. {rec}")
        print()

    print(f"ℹ️  诊断完成 · {stable}\n")


def format_json(results: list[ProbeResult], symptom: str, elapsed: float):
    output = {
        "diagnose_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symptom": symptom,
        "elapsed": round(elapsed, 1),
        "probes": [
            {
                "name": r.name,
                "status": r.status,
                "summary": r.summary,
                "details": r.details,
                "recommendations": r.recommendations,
            }
            for r in results
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🔍 astra-sre diagnose — 子代理并行排查框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Modes: triage(t), gateway(g), services(s), network(n), system(sys)\n"
               "Examples:\n"
               "  %(prog)s                          # 全量诊断\n"
               "  %(prog)s --mode network,gateway   # 只查网络+Gateway\n"
               "  %(prog)s --mode t,g,s             # 短名\n"
               "  %(prog)s --symptom \"无法解密\"     # 带症状\n"
               "  %(prog)s --json                  # JSON 输出",
    )
    parser.add_argument("--mode", default="all", help="诊断维度 (逗号分隔, 默认 all)")
    parser.add_argument("--symptom", default="", help="症状描述（传给 triage 搜历史案例）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    # Resolve probe names
    if args.mode == "all":
        selected = list(PROBES.keys())
    else:
        raw = [s.strip() for s in args.mode.split(",")]
        selected = []
        for r in raw:
            resolved = SHORT_NAMES.get(r, r)
            if resolved in PROBES:
                selected.append(resolved)
            else:
                print(f"⚠️ 未知维度: {r} (可选: {', '.join(PROBES.keys())})", file=sys.stderr)

    if not selected:
        print("❌ 无有效诊断维度", file=sys.stderr)
        sys.exit(1)

    # Run probes in parallel
    start = time.time()
    results: list[ProbeResult] = []
    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        futures = {}
        for name in selected:
            probe_fn = PROBES[name]
            if name == "triage":
                futures[executor.submit(probe_fn, args.symptom)] = name
            else:
                futures[executor.submit(probe_fn)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result(timeout=TIMEOUT + 5)
                results.append(result)
            except Exception as e:
                results.append(ProbeResult(name, "error", f"探针异常: {e}"))
    elapsed = time.time() - start

    # Sort by severity (error first, then warn, then ok)
    severity_order = {"error": 0, "warn": 1, "ok": 2}
    results.sort(key=lambda r: severity_order.get(r.status, 3))

    # Output
    if args.json:
        format_json(results, args.symptom, elapsed)
    else:
        format_markdown(results, args.symptom, elapsed)

    # Exit code
    has_error = any(r.status == "error" for r in results)
    sys.exit(2 if has_error else 0)


if __name__ == "__main__":
    main()
