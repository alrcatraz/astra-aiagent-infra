#!/usr/bin/env python3
"""
astra-sre health-scan.py
Phase 1: 全设备统一巡检 + 分级报告

Usage:
    ./health-scan.py                    # 默认 markdown 输出
    ./health-scan.py --brief            # 只输出摘要
    ./health-scan.py --output json      # JSON 格式
"""

import argparse
import os
import subprocess
import sys
import socket
import time
import yaml
from dataclasses import dataclass, field
from typing import Optional

# ── Config ──────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'devices.yaml')
SSH_DIR = os.path.expanduser('~/.ssh')
TIMEOUT = 10  # per-host SSH timeout

# ── Data models ─────────────────────────────────────────────
@dataclass
class CheckResult:
    disk_pct: Optional[int] = None
    mem_pct: Optional[int] = None
    uptime_str: str = '?'
    load_str: str = '?'
    services_ok: int = 0
    services_total: int = 0
    reachable: bool = False
    error: str = ''

@dataclass
class Finding:
    severity: int  # 0=ok, 1=P3, 2=P2, 3=P1
    device: str
    message: str

    @property
    def emoji(self): return {0: '✅', 1: '🔵', 2: '🟡', 3: '🟠'}[self.severity]

    @property
    def label(self): return {0: 'OK', 1: 'P3', 2: 'P2', 3: 'P1'}[self.severity]


# ── SSH helpers ─────────────────────────────────────────────
def ssh_cmd(target: str, key: str, command: str) -> str:
    """Run a command on a remote host and return stdout."""
    if target == 'localhost':
        result = subprocess.run(
            ['bash', '-c', command],
            capture_output=True, text=True, timeout=TIMEOUT
        )
        return result.stdout

    # Build SSH args
    ssh_args = [
        'ssh',
        '-o', 'ConnectTimeout=8',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'BatchMode=yes',
        '-o', 'PasswordAuthentication=no',
    ]

    # Parse target: could be alias, or user@host, or user@host:port
    port = None
    if ':' in target and '@' in target:
        # user@host:port
        target, port_str = target.rsplit(':', 1)
        if port_str.isdigit():
            port = int(port_str)
    elif target.count(':') > 0:
        # alias
        pass

    if key and key != 'pending':
        key_path = os.path.join(SSH_DIR, key)
        if os.path.exists(key_path):
            ssh_args.extend(['-i', key_path])

    if port:
        ssh_args.extend(['-p', str(port)])

    ssh_args.append(target)
    ssh_args.append(command)

    try:
        result = subprocess.run(ssh_args, capture_output=True, text=True, timeout=TIMEOUT)
        return result.stdout
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        return ''
    except FileNotFoundError:
        return ''


# ── Per-device scanner ──────────────────────────────────────
def scan_device(name: str, ssh_target: str, key: str, checks: list[dict]) -> tuple[CheckResult, list[Finding]]:
    """Scan one device and return results + findings."""
    result = CheckResult()
    findings = []

    # Connectivity check
    if ssh_target != 'localhost':
        # Extract IP for ping
        ip = ssh_target.split('@')[-1].split(':')[0]
        try:
            ping = subprocess.run(
                ['ping', '-c', '1', '-W', '3', ip],
                capture_output=True, timeout=5
            )
            result.reachable = ping.returncode == 0
        except subprocess.TimeoutExpired:
            result.reachable = False
    else:
        result.reachable = True

    # ── Disk ──
    disk_out = ssh_cmd(ssh_target, key, "df / --output=pcent | tail -1 | tr -d ' %'")
    if disk_out.strip().isdigit():
        result.disk_pct = int(disk_out.strip())

    # ── Memory ──
    mem_out = ssh_cmd(ssh_target, key, r"""free -m | awk '/^Mem:/{printf "%d %d", $3, $2}'""")
    if mem_out.strip():
        parts = mem_out.strip().split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            used, total = int(parts[0]), int(parts[1])
            if total > 0:
                result.mem_pct = int(used * 100 / total)

    # ── Uptime & Load ──
    uptime_out = ssh_cmd(ssh_target, key, 'uptime')
    if uptime_out:
        if 'up' in uptime_out:
            result.uptime_str = uptime_out.split('up')[1].split(',')[0].strip()[:30]
        if 'load average:' in uptime_out:
            result.load_str = uptime_out.split('load average:')[1].strip()[:20]

    # ── Service checks from config ──
    svc_checks = []
    for c in checks:
        if isinstance(c, dict) and 'systemd' in c:
            svc_checks = c['systemd']
            if isinstance(svc_checks, str):
                svc_checks = [s.strip() for s in svc_checks.split(',')]

    if svc_checks:
        result.services_total = len(svc_checks)
        for svc in svc_checks:
            out = ssh_cmd(ssh_target, key, f"systemctl is-active {svc} 2>/dev/null || echo 'inactive'")
            if 'active' in out:
                result.services_ok += 1

    # ── Disk threshold checks ──
    disk_warn = 85
    disk_crit = 92
    for c in checks:
        if isinstance(c, dict):
            if 'disk_warn' in c:
                disk_warn = int(c['disk_warn'])
            if 'disk_crit' in c:
                disk_crit = int(c['disk_crit'])

    if result.disk_pct is not None:
        if result.disk_pct >= disk_crit:
            findings.append(Finding(3, name, f"磁盘 {result.disk_pct}% (超过警戒线 {disk_crit}%)"))
        elif result.disk_pct >= disk_warn:
            findings.append(Finding(1, name, f"磁盘 {result.disk_pct}%"))

    # ── Memory threshold (80/92) ──
    if result.mem_pct is not None and result.mem_pct > 92:
        findings.append(Finding(2, name, f"内存 {result.mem_pct}%"))
    elif result.mem_pct is not None and result.mem_pct > 80:
        findings.append(Finding(1, name, f"内存 {result.mem_pct}%"))

    # ── Service failures ──
    if result.services_total > 0 and result.services_ok < result.services_total:
        down = result.services_total - result.services_ok
        findings.append(Finding(2, name, f"{down}/{result.services_total} 服务离线"))

    return result, findings


# ── Output formatters ──────────────────────────────────────
def format_markdown(device_results: list[tuple], all_findings: list[Finding], scan_time: str):
    """Print markdown-formatted report."""
    print(f"\n📊 **astra-sre 全设备巡检 · {scan_time}**")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    for name, result, findings in device_results:
        status = '✅' if not any(f.severity >= 2 for f in findings) else \
                 '⚠️' if not any(f.severity >= 3 for f in findings) else '❌'

        parts = [status, f"**{name}**"]

        if result.load_str != '?':
            parts.append(f"负载:{result.load_str}")
        if result.disk_pct is not None:
            parts.append(f"磁盘:{result.disk_pct}%")
        if result.mem_pct is not None:
            parts.append(f"内存:{result.mem_pct}%")
        parts.append(f"运行:{result.uptime_str}")

        print("  " + " · ".join(parts))

    print("\n📋 **巡检摘要**")
    print("━━━━━━━━━")

    if not all_findings:
        print("  ✅ 全部正常，无异常项")
    else:
        for sev in [3, 2, 1]:
            items = [f for f in all_findings if f.severity == sev]
            if items:
                label = {3: '🟠 P1', 2: '🟡 P2', 1: '🔵 P3'}
                print(f"  **{label[sev]}** ({len(items)} 项)")
                for f in items:
                    print(f"    · {f.device}: {f.message}")

    print(f"\n  ℹ️  扫描完成 · {time.strftime('%Y-%m-%d %H:%M:%S')}")


def format_json(device_results: list[tuple], all_findings: list[Finding], scan_time: str):
    """Print JSON-formatted report."""
    import json
    report = {
        'scan_time': scan_time,
        'devices': [],
        'findings': [],
    }
    for name, result, findings in device_results:
        d = {
            'name': name,
            'reachable': result.reachable,
            'disk_pct': result.disk_pct,
            'mem_pct': result.mem_pct,
            'load': result.load_str,
            'uptime': result.uptime_str,
            'services': f"{result.services_ok}/{result.services_total}",
        }
        report['devices'].append(d)

    for f in all_findings:
        report['findings'].append({
            'severity': f.severity,
            'device': f.device,
            'message': f.message,
        })

    print(json.dumps(report, indent=2, ensure_ascii=False))


# ── Main ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='astra-sre 全设备巡检')
    parser.add_argument('--brief', action='store_true', help='只输出摘要')
    parser.add_argument('--output', choices=['markdown', 'json'], default='markdown', help='输出格式')
    args = parser.parse_args()

    # Load config
    if not os.path.exists(CONFIG_PATH):
        print(f"{'❌'} 配置未找到: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    devices = config.get('devices', [])
    if not devices:
        print(f"{'❌'} 配置中无设备", file=sys.stderr)
        sys.exit(1)

    scan_time = time.strftime('%Y-%m-%d %H:%M:%S')
    device_results = []
    all_findings = []

    for dev in devices:
        name = dev['name']
        ssh_target = dev.get('ssh', 'localhost')
        key = dev.get('key', '')
        checks = dev.get('checks', [])

        result, findings = scan_device(name, ssh_target, key, checks)
        device_results.append((name, result, findings))
        all_findings.extend(findings)

    # Sort findings by severity desc
    all_findings.sort(key=lambda f: f.severity, reverse=True)

    # Output
    if args.output == 'json':
        format_json(device_results, all_findings, scan_time)
    else:
        format_markdown(device_results, all_findings, scan_time)

    # Exit code
    p1_count = sum(1 for f in all_findings if f.severity >= 3)
    sys.exit(2 if p1_count > 0 else 0)


if __name__ == '__main__':
    main()
