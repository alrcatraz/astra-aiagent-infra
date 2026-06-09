# astra-sre Phase 3 — 自动修复框架设计

> 版本: 1.0
> 日期: 2026-06-07
> 状态: 设计定稿

---

## 核心原则

不二选一，渐进过渡：先写 recipe（带触发条件和决策点标记），预留 auto-safe 扩展空间。信任建立后再逐步放开安全操作的自动执行。

## 修复等级（L1/L2/L3）

按**影响面**而非操作本身来分级：

| 等级 | 定义 | 示例 | 执行策略 |
|:----:|:----|:-----|:--------|
| **L1** 无感修复 | 用户完全感知不到，无服务影响 | 改配置、清缓存、重发通知 | ✅ 完全自动执行 |
| **L2** 有感但无风险 | 影响短暂或对非关键服务 | 重启非关键服务、跑只读诊断脚本 | ✅ 自动执行 + 事后通知你 |
| **L3** 有风险或不可逆 | 可能导致数据丢失或服务中断 | 删数据、改 token、重建服务、重启关键服务 | 🛑 必须你批准 |

## 修复流程

```
出问题 ──→ diagnose.sh 并行诊断
              │
              ▼
        查 sre_incidents ──→ 有匹配？
              │                    │
            没有                  有
              │                    │
              ▼                    ▼
         找你一起看          判断修复级别
         排查+修复              │
              │           ┌─────┼─────┐
              │           │     │     │
              │          L1   L2   L3
              │        自动  自动+  找你
              │        执行  通知  确认
              │           │     │     │
              │           └─────┼─────┘
              │                 │
              │           验证探针 ← 关键！
              │           │       │
              │         正常    更糟
              │           │       │
              │          ✅   回滚/通知
              │
              ▼
       记录到 sre_incidents
              │
       同一标签出现两次？──→ learn.py 建议固化到 sub-skill
```

## 验证探针

每个自动修复步骤后必须紧跟验证：

- 复用 `diagnose.sh` 的单个 probe（如 `--mode gateway`）
- 对比修复前后的状态
- 如果修复后的状态比修复前更差 → 自动触发 **回滚机制**或**紧急通知**

## 修复锁

同一类问题的修复加锁（按标签）。

### 锁的实现

```
锁文件: /tmp/astra-sre-lock-<tag>.lock
内容:   PID + 锁定时间（秒级时间戳）
```

### 加锁/解锁逻辑

```
加锁时:
  1. 锁文件存在？
     ├─ 否 → 创建锁（写入当前 PID + 时间戳）→ 获得锁 ✅
     └─ 是 → 读取锁内容
              ├─ PID 仍存活 → 被其他修复持有，排队 ⏳
              └─ PID 已死  → 残余锁！清除旧锁，获取新锁 ✅

解锁时:
  清除锁文件（无论成功失败都要执行）
```

### 关键设计决策

- **PID 存活检测**用 `kill -0 <PID>`（不发送信号，只检测进程是否存在）
- **没有硬超时** —— 修复任务可能跑几个小时（如 `zypper dup`、全量 E2EE 恢复），只要 PID 活着锁就有效
- **残余锁自动清理** —— 唯一判断标准：PID 死了就是残余锁，不管锁文件是 1 分钟前还是 1 天前创建的
- **锁龄监控（可选，非强制）** —— 锁龄超过 30 分钟时在日志中记录一条提示，方便排查"是不是卡住了"，但不强制解锁

## Sub-skill 模板

每个修复子 skill 应包含以下字段：

```yaml
name: astra-sre-fix-<problem>
level: L1|L2|L3          # 修复等级
triggers:                 # 触发条件（diagnose.sh 输出匹配）
  - <probe>: <pattern>
safety:                   # 安全说明
  rollback: <如何回滚>
  risks: [<风险列表>]
steps:                    # 修复步骤
  - <step> [auto|gate]    # auto=自动, gate=需你确认
verify: <验证探针>
```

## 已有 sub-skill 评估

| Sub-skill | 当前等级 | 建议等级 | 理由 |
|:----------|:--------:|:--------:|:-----|
| astra-sre-fix-e2ee | L2/L3 ✅ | L2/L3 | L2: 重新共享密钥（e2ee-repair-keys.py、e2ee-request-keys.py）。L3: 完全恢复（DB 修改、token 轮换、crypto.db 删除）|
| astra-sre-restart-service | L2/L3 ✅ | L2/L3 | 非关键服务重启 L2，关键服务（Gateway/PostgreSQL）重启 L3 |
| full-e2ee-recovery-after-server-rebuild | L1/L2/L3 ✅ | L1/L2/L3 | L1: set presence、verify。L2: 新 token、启动 Gateway。L3: 删 crypto.db、改 .env、用户操作 |

## 核心 SRE 基础设施（已纳入 astra-sre）

| Skill | 原分类 | 在 SRE 中的角色 | 说明 |
|:------|:------:|:---------------|:-----|
| service-inventory | devops | **数据层** — 服务注册表 + 健康历史 | `healthcheck.py` 和 `diagnose.sh` 的底层依赖。`mgmt.services` 表管理所有服务状态 |
| infrastructure-device-inventory | devops | **资产层** — 设备清单 + 组网拓扑 | `devices.yaml` 的数据来源。8 台设备的 SSH 路径、组网地址、访问优先级 |

## 外部引用的 playbook（保持独立）

| Skill | 原分类 | 与 SRE 的关系 | 优先级 |
|:------|:------:|:-------------|:-----:|
| server-restart-recovery | devops | 服务器重启手册，含 E2EE 恢复交叉引用 | 🟡 |
| server-health-audit | devops | 健康审计，diagnose.sh 的补充 | 🟡 |
| crash-marker-pattern | devops | 看门狗通知模式 | 🟢 |
| pre-upgrade-server-backup | devops | VPS 升配备份流程 | 🟢 |
| matrix-gateway-setup | devops | Gateway 部署 + E2EE 初始设置 | 🟢 |

## 外部修复经验记录

在 SRE 框架外发生的修复，通过以下方式进入 sre_incidents：

| 场景 | 触发 | 我的行为 |
|:-----|:-----|:---------|
| 我们一起排查修好 | 我说"搞定了"之后 | 主动问"要记进 sre_incidents 吗？" |
| 你修好了告诉我 | 你说修好了 | 追问根因，判断是否值得记，问你要不要入库 |
| 同事/他人的经验 | 你说"这个你收一下"或"这个你看看" | 提取关键信息，写入 sre_incidents |
| 确认记录 | 你说"可以"/"好"/"嗯" | 执行写入 |
| 跳过 | 你说"不用"/"没必要" | 不记 |

> 不需要特定关键词或 emoji。我来承担识别和提问的责任，你只需要像平常一样说话。
