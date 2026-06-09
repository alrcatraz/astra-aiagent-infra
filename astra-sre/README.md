# astra-sre

> 自有基础设施的 SRE 协调层 — 统一巡检、诊断、修复与学习
>
> 隶属于 [Astra-Lab.org](https://astra-lab.org) 项目生态

---

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                   astra-sre                          │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ 资产层    │  │ 数据层    │  │ 诊断层            │  │
│  │ device   │  │ service  │  │ triage + diagnose │  │
│  │ inventory│  │ inventory│  │                   │  │
│  └──────────┘  └──────────┘  └────────┬─────────┘  │
│                                       │             │
│  ┌────────────────────────────────────┘             │
│  │                                                   │
│  ▼                                                   │
│  ┌──────────────────────────────────────────────┐    │
│  │              修复层 (sub-skills)               │    │
│  │  fix-e2ee · restart-service · fix-gfw        │    │
│  │  fix-mcp · fix-vps-recovery                  │    │
│  └──────────────────────────────────────────────┘    │
│                          │                           │
│  ┌───────────────────────┘                          │
│  ▼                                                   │
│  ┌──────────────────────────────────────────────┐    │
│  │              学习层 (learn.py)                 │    │
│  │  两次原则 → 自动建议新 sub-skill              │    │
│  └──────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## Phase 1 — 全设备巡检 🟢

每日 08:00 自动扫描 8 台设备的磁盘、内存、系统服务状态，分级报告。

| 文件 | 说明 |
|:-----|:------|
| `scripts/health-scan.py` | Python 巡检主脚本（支持 markdown/JSON） |
| `scripts/health-scan.sh` | Shell fallback |
| `config/devices.yaml` | 8 台设备配置（vps-hk/uk/ds425plus/suset01/homecentre01/susetlearn00/fedoratg/openwrt） |

**cron:** 每日 08:00 → Home 📊 线程

---

## Phase 2 — 诊断与知识沉淀 🟢

| 文件 | 说明 |
|:-----|:------|
| `scripts/triage.py` | 输入症状，搜索 `sre_incidents` 找历史案例 |
| `scripts/diagnose.py` | 5 路并行诊断（triage/gateway/services/network/system） |
| `scripts/diagnose.sh` | CLI 入口（自动 source .env） |

**知识库:** `sre_incidents`（PostgreSQL FTS）— 10 条事故记录

---

## Phase 3 — 自动修复框架 🟢

### 修复等级

| 等级 | 策略 |
|:----:|:------|
| **L1** 🔵 | 完全自动执行，无感 |
| **L2** 🟡 | 自动执行 + 事后通知 |
| **L3** 🔴 | 必须你确认 |
| **L3** 🧑 | 需你亲自操作 |

### 子 skill 清单

| Skill | 等级 | 说明 |
|:------|:----:|:------|
| `astra-sre-fix-e2ee` | L2/L3 | E2EE 日常修复（L2: 重分享密钥, L3: 全量恢复） |
| `astra-sre-restart-service` | L2/L3 | 服务重启（L2: 非关键服务, L3: Gateway/PostgreSQL） |
| `astra-sre-fix-gfw` | L2 | GFW 阻断诊断与降级 |
| `astra-sre-fix-mcp` | L2 | MCP 进程审计与清理 |
| `astra-sre-fix-vps-recovery` | L2/L3 | VPS 升配/重建后恢复 |

### 核心 SRE 基础设施

| Skill | 角色 | 说明 |
|:------|:-----|:------|
| service-inventory | 数据层 | `mgmt.services` + `mgmt.health_log` 管理 |
| infrastructure-device-inventory | 资产层 | 8 台设备的组网路径与访问方式 |

### 锁机制

修复锁用 PID 文件实现（`/tmp/astra-sre-lock-<tag>.lock`）：
- PID 活着 → 锁有效
- PID 死了 → 残余锁，自动清理
- 没有硬超时（修复可能跑几个小时）

---

## Phase 4 — 学习闭环 🟢

| 文件 | 说明 |
|:-----|:------|
| `scripts/learn.py` | "两次原则" — 检测重复模式，建议新 sub-skill |

**cron:** 每月 1 日 09:00 随 `astra-sre-refresh.sh` 自动运行

---

## 设计文档

| 文件 | 说明 |
|:-----|:------|
| `references/phase3-design.md` | 修复框架设计（含锁机制、验证探针、分级策略） |
| `references/format-convention.md` | 项目格式约定（YAML/JSON/TOML） |

---

## 维护

| 任务 | 频率 | 方式 |
|:-----|:----:|:-----|
| 全设备巡检 | 每日 08:00 | `health-scan.py` → Home 线程 |
| Hermes 版本 + learn.py | 每月 1 日 09:00 | `astra-sre-refresh.sh` → 没事不出声 |
| sre_incidents 更新 | 事故后 | 手动写入（参考 `kb_add` 格式） |

---

## 快速参考

```bash
# 全设备巡检
./scripts/health-scan.py
./scripts/health-scan.py --json

# 搜历史案例
./scripts/triage.py "E2EE 无法解密"
./scripts/triage.py --list

# 并行诊断
./scripts/diagnose.sh
./scripts/diagnose.sh --mode network,gateway --symptom "sync error"

# 两次原则检测
./scripts/learn.py
./scripts/learn.py --cron  # 只在新建议时输出
```

---

## 依赖

- Python 3.11+ / uv
- PostgreSQL 16 (`astra_kb` 数据库)
- psycopg2-binary
- Hermes Agent (MCP 工具: `astra-knowledge-base`)
- 目标设备: SSH key 认证 + systemd
