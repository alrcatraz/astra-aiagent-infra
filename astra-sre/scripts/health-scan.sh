#!/bin/bash
# astra-sre health-scan.sh
# Phase 1: 全设备统一巡检 + 分级报告
# Usage: ./health-scan.sh [--brief] [--output markdown|json]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG="$PROJECT_DIR/config/devices.yaml"
SUMMARY_FILE="/tmp/astra-sre-scan-$$.tmp"
RESULT_FILE=""

# ── 颜色 & 图标 ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ICON_OK="✅"; ICON_WARN="⚠️"; ICON_CRIT="❌"; ICON_INFO="ℹ️"

# ── 严重等级 ─────────────────────────────────────────────────
P_LEVELS=("" "🔴 P0" "🟠 P1" "🟡 P2" "🔵 P3")

# ── 工具函数 ──────────────────────────────────────────────────
die() { echo -e "$ICON_CRIT $*" >&2; exit 1; }

log_info() { echo -e "  ${ICON_INFO} $*"; }
log_ok()  { echo -e "  ${ICON_OK} ${GREEN}$*${NC}"; }
log_warn(){ echo -e "  ${ICON_WARN} ${YELLOW}$*${NC}"; }
log_crit(){ echo -e "  ${ICON_CRIT} ${RED}$*${NC}"; }

collect_p3() { echo "    - $1" >> "$SUMMARY_FILE"; }
collect_p2() { echo "  - $1" >> "$SUMMARY_FILE"; }
collect_p1() { echo "- $1" >> "$SUMMARY_FILE"; }

# ── Parse YAML: devices list ──────────────────────────────────
parse_devices() {
  # Extract device blocks from YAML - 简单解析，不依赖 yq
  awk '/^  - name:/{name=$NF}
       /^    role:/{role=substr($0,index($0,$NF))}
       /^    os:/{os=substr($0,index($0,$NF))}
       /^    ssh:/{ssh=substr($0,index($0,$NF))}
       /^    checks:/{p=1; next}
       p && /^      - /{
         gsub(/[][]/,"")
         print name":"ssh":"os":"$0
       }' "$CONFIG" 2>/dev/null || return 1
}

# ── SSH with timeout wrapper ──────────────────────────────────
ssh_run() {
  local host="$1"; shift
  local key="$1"; shift
  local cmd="$*"

  local ssh_opt=(-o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -o BatchMode=yes)
  if [ -n "$key" ] && [ "$key" != "pending" ]; then
    ssh_opt+=(-i "$HOME/.ssh/$key")
  fi
  # 处理别名和完整地址
  # If the host looks like an alias (no @), try direct ssh alias
  # If it has user@host:port format, split it
  local ssh_target="$host"
  if echo "$host" | grep -q ':' && ! echo "$host" | grep -q '@'; then
    # host:port format
    local port="${host##*:}"
    local h="${host%:*}"
    ssh_target="$h"
    ssh_opt+=(-p "$port")
  fi

  ssh "${ssh_opt[@]}" "$ssh_target" "$cmd" 2>/dev/null
}

# ── 单机巡检 ──────────────────────────────────────────────────
scan_device() {
  local name="$1"; shift
  local ssh_target="$1"; shift
  local key="$1"; shift

  local disk_pct="?" mem_pct="?" uptime_str="?" load_str="?" services_ok=0 services_total=0
  local disk_note="" mem_note="" uptime_note="" svc_note=""
  local device_ok=true

  # Skip if no SSH target
  if [ "$ssh_target" = "localhost" ]; then
    # Local check
    disk_pct=$(df / --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
    mem_total=$(free -m | awk '/^Mem:/{print $2}')
    mem_used=$(free -m | awk '/^Mem:/{print $3}')
    mem_pct=$(( mem_used * 100 / (mem_total + 1) ))
    uptime_str=$(uptime -p 2>/dev/null | sed 's/up //')
    load_str=$(uptime | awk -F'load average:' '{print $2}' | xargs)
    return
  fi

  # Quick connectivity test
  local ping_ok=false
  local ssh_ip="${ssh_target#*@}"
  ssh_ip="${ssh_ip%:*}"  # strip port
  if ping -c 1 -W 3 "$ssh_ip" >/dev/null 2>&1; then
    ping_ok=true
  fi

  # ── Disk usage ──
  local disk_out
  disk_out=$(ssh_run "$ssh_target" "$key" "df / --output=pcent,target 2>/dev/null | tail -1" 2>/dev/null) || true
  if [ -n "$disk_out" ]; then
    disk_pct=$(echo "$disk_out" | awk '{print $1}' | tr -d ' %')
  fi

  # ── Memory ──
  local mem_out
  mem_out=$(ssh_run "$ssh_target" "$key" "free -m | awk '/^Mem:/{printf \"%d %d\", \$3, \$2}'" 2>/dev/null) || true
  if [ -n "$mem_out" ]; then
    local mem_used=$(echo "$mem_out" | awk '{print $1}')
    local mem_total=$(echo "$mem_out" | awk '{print $2}')
    [ "$mem_total" -gt 0 ] && mem_pct=$(( mem_used * 100 / mem_total )) || mem_pct=0
  fi

  # ── Uptime & load ──
  local sys_out
  sys_out=$(ssh_run "$ssh_target" "$key" "uptime" 2>/dev/null) || true
  if [ -n "$sys_out" ]; then
    uptime_str=$(echo "$sys_out" | sed 's/.*up //' | sed 's/,.*//')
    load_str=$(echo "$sys_out" | awk -F'load average:' '{print $2}' | xargs)
  fi

  # ── Service checks ──
  local svc_out
  svc_out=$(ssh_run "$ssh_target" "$key" "
    for svc in postgresql matrix-synapse nginx sshd easytier tailscaled NetworkManager; do
      systemctl is-active \"\$svc\" 2>/dev/null && echo \"\$svc:active\" || echo \"\$svc:inactive\"
    done
  " 2>/dev/null) || true

  while IFS=: read -r svc status; do
    [ -n "$svc" ] && services_total=$((services_total + 1))
    [ "$status" = "active" ] && services_ok=$((services_ok + 1))
  done <<< "$svc_out"

  # ── 分级收集 ──
  # P3: disk > 85%
  if [ "$disk_pct" != "?" ] && [ "$disk_pct" -gt 85 ] 2>/dev/null; then
    if [ "$disk_pct" -gt 92 ]; then
      collect_p1 "$name: 磁盘 ${disk_pct}% (严重)"
      device_ok=false
    else
      collect_p3 "$name: 磁盘 ${disk_pct}%"
    fi
  fi

  # P3: memory > 80%
  if [ "$mem_pct" != "?" ] && [ "$mem_pct" -gt 80 ] 2>/dev/null; then
    collect_p3 "$name: 内存 ${mem_pct}%"
  fi

  # P1: services down
  if [ "$services_total" -gt 0 ] && [ "$services_ok" -lt "$services_total" ]; then
    local down=$((services_total - services_ok))
    collect_p2 "$name: $down/$services_total 服务离线"
    device_ok=false
  fi

  # ── 汇总结果 ──
  local status_icon="$ICON_OK"
  local status_color="${GREEN}"
  if [ "$disk_pct" != "?" ] && [ "$disk_pct" -gt 92 ] 2>/dev/null; then
    status_icon="$ICON_CRIT"; status_color="${RED}"
  elif [ "$mem_pct" != "?" ] && [ "$mem_pct" -gt 90 ] 2>/dev/null; then
    status_icon="$ICON_CRIT"; status_color="${RED}"
  elif [ "$services_total" -gt 0 ] && [ "$services_ok" -lt "$services_total" ]; then
    status_icon="$ICON_WARN"; status_color="${YELLOW}"
  elif [ "$disk_pct" != "?" ] && [ "$disk_pct" -gt 85 ] 2>/dev/null; then
    status_icon="$ICON_WARN"; status_color="${YELLOW}"
  fi

  # Output for summary
  printf "%-16s %b CPU/负载:%-12s 磁盘:%-4s 内存:%-4s 运行:%s\n" \
    "$name" "$status_icon" "$load_str" "${disk_pct}%" "${mem_pct}%" "$uptime_str"
}

# ── 主函数 ────────────────────────────────────────────────────
main() {
  local brief=false
  local format="markdown"

  while [ $# -gt 0 ]; do
    case "$1" in
      --brief) brief=true ;;
      --output) format="$2"; shift ;;
      *) die "Unknown option: $1" ;;
    esac
    shift
  done

  # Init summary file
  : > "$SUMMARY_FILE"

  # Header
  local scan_time
  scan_time=$(date '+%Y-%m-%d %H:%M:%S')
  echo ""
  echo -e "${BOLD}📊 astra-sre 全设备巡检 · $scan_time${NC}"
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""

  # Parse device list from config
  while IFS=':' read -r name ssh_target os check_line; do
    [ -z "$name" ] && continue

    # Extract check type and value from the check line
    check_type=$(echo "$check_line" | grep -oP '^\s+-\s+\K\w+' || echo "")
    check_value=$(echo "$check_line" | grep -oP '(?<=: )\S+' || echo "")

    # Only process each device once (deduplicate by name)
    # Use associative array to track processed devices
    if [ "${processed[$name]:-}" = "1" ]; then
      continue
    fi
    processed[$name]=1

    # Skip devices clearly offline (based on connectivity test)
    echo -e "${BOLD}🔍 扫描: $name${NC} ($os)"
    scan_device "$name" "$ssh_target" "$(echo "$check_line" | grep -oP 'key: \K\S+' || echo "")"
    echo ""
  done < <(parse_devices)

  # ── 汇总报告 ──────────────────────────────────────────────────
  echo -e "${BOLD}📋 巡检摘要${NC}"
  echo -e "${BOLD}━━━━━━━━━━━${NC}"

  local p1_count=0 p2_count=0 p3_count=0
  p1_count=$(grep -cP '^- ' "$SUMMARY_FILE" 2>/dev/null || true)
  p2_count=$(grep -cP '^  - ' "$SUMMARY_FILE" 2>/dev/null || true)
  p3_count=$(grep -cP '^    - ' "$SUMMARY_FILE" 2>/dev/null || true)

  if [ ! -s "$SUMMARY_FILE" ]; then
    echo -e "  ${GREEN}${ICON_OK} 全部正常，无异常项${NC}"
  else
    [ "$p1_count" -gt 0 ] && echo -e "  ${RED}🟠 P1: $p1_count 项${NC}"
    [ "$p2_count" -gt 0 ] && echo -e "  ${YELLOW}🟡 P2: $p2_count 项${NC}"
    [ "$p3_count" -gt 0 ] && echo -e "  ${BLUE}🔵 P3: $p3_count 项${NC}"
    echo ""
    echo -e "${BOLD}详情:${NC}"
    cat "$SUMMARY_FILE"
  fi

  # ── 耗时 ──────────────────────────────────────────────────────
  echo ""
  local end_time
  end_time=$(date '+%Y-%m-%d %H:%M:%S')
  echo -e "${CYAN}ℹ️  扫描完成 · $end_time${NC}"

  # Cleanup
  rm -f "$SUMMARY_FILE"
}

main "$@"
