---
name: astra-sre-restart-service
description: "通用服务重启诊断与修复 — 检测宕机服务、评估影响等级、执行重启、验证恢复"
version: 1.0.0
author: ANGELIA
platforms: [linux]
level: L2/L3
related_skills:
  - astra-sre-fix-e2ee
  - service-inventory
---

# astra-sre-restart-service — 通用服务重启子 skill

> 当 diagnose.sh 检测到服务宕机时加载此 skill。
> 配合 Phase 3 修复框架使用。

---

## 触发条件

| 探针 | 匹配模式 | 说明 |
|:----|:--------|:-----|
| `diagnose services` | `❌ <service>: inactive` 或 `❌ <service>: failed` | 服务不在运行 |
| `diagnose gateway` | Gateway 非 active | Gateway 挂了 |
| `diagnose network` | Synapse HTTP 非 200 | Matrix 服务不可达 |
| 用户直接报告 | "XXX 崩了/挂了/连不上" | 人工触发 |

---

## 服务影响等级

| 服务 | 默认等级 | 说明 |
|:-----|:-------:|:-----|
| hermes-gateway | **L3** 🔴 | 重启会中断当前对话，需你确认 |
| postgresql | **L3** 🔴 | 所有依赖 PG 的服务一起断 |
| searxng-core | **L2** 🟡 | 搜索暂时不可用，web_search 降级 |
| mcp-server-* | **L2** 🟡 | 单个 MCP 服务不可用，不影响其他 |
| easytier / tailscaled | **L3** 🔴 | 组网断开可能影响远程访问 |
| sshd | **L2** 🟡 | SSH 连接中断但不影响已有会话 |

---

## 诊断流程

### 第一步：确认服务状态

```bash
systemctl is-active <service>       # 系统服务
systemctl --user is-active <service> # 用户服务
journalctl -u <service> -n 20 --no-pager  # 看最近日志
```

### 第二步：判断影响范围

```bash
# 查询该服务有哪些依赖者
# PostgreSQL: 所有 MCP、Hermes Gateway（知识库）
# Gateway: 所有平台的消息收发
# SearXNG: web_search 工具
```

### 第三步：确认不是已知模式

搜索 sre_incidents：`kb_search("sre_incidents", "<service> restart|down|crash")`

---

## 修复步骤

### L2 修复（自动 + 通知）

> 适用于非关键服务，自动执行后通知你。

```bash
# 1. 尝试优雅停止（给 10 秒）
systemctl stop <service> 2>/dev/null || \
systemctl --user stop <service> 2>/dev/null
sleep 2

# 2. 重置失败状态（如果有 failed）
systemctl reset-failed <service> 2>/dev/null || \
systemctl --user reset-failed <service> 2>/dev/null

# 3. 启动
systemctl start <service> 2>/dev/null || \
systemctl --user start <service> 2>/dev/null
```

**验证：** `systemctl is-active <service>` 应为 `active`

### L3 修复（需要你确认）

> 适用于关键服务，必须经过你批准。

1. 通知你：`<service> 宕机，需要重启。当前连接可能中断。批准吗？`
2. 你确认后执行重启
3. 重启后自动验证
4. 汇报结果

---

## 验证探针

```bash
# 服务存活
systemctl is-active <service> || systemctl --user is-active <service>

# 端口监听（如果有已知端口）
ss -tlnp | grep <port> || true

# 进程存在
pgrep -f <service> > /dev/null && echo "process: alive" || echo "process: dead"
```

### 验证失败处理

如果重启后服务仍未恢复：

1. **首次失败** → 等 5 秒后重试一次
2. **二次失败** → 收集 journalctl 日志 → 搜索 sre_incidents → 通知你
3. **通知内容**：服务名、重启次数、journalctl 最后 10 行、sre_incidents 匹配结果

---

## 已知陷阱

| 陷阱 | 说明 |
|:----|:------|
| systemctl --user 卡死 | 进程处于 'deactivating' 状态时 systemctl stop 可能 hang。用 pkill + reset-failed 绕过 |
| Gateway 重启断对话 | 通过 Gateway 通信的会话中重启 Gateway → 会话中断。L3 必须通知你 |
| 依赖链 | 重启 PostgreSQL 会导致所有依赖它的服务一起断开。先查依赖再操作 |
| 启动后不等验证 | 某些服务启动需要时间（如 PostgreSQL），启动后等 5 秒再验证 |
| 残余锁文件 | systemctl reset-failed 清除 systemd 层面的失败状态，但不会清理进程锁文件 |

---

## 验证

1. ✅ `systemctl is-active <service>` → active
2. ✅ 端口监听正常（如有）
3. ✅ 进程运行中
4. ✅ 如果之前 diagnose.sh 报告的，重新跑验证
