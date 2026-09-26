# 舰队存储/业务分层 + KB 定位定案（2026-09-26 与用户共同推导）

> 状态：原则已定案；迁移未执行。下次在 Hermes 桌面端继续讨论并实践具体迁移。
> 本文件 = 该讨论的底稿与依据存档。

## 一、分层原则（定案）

- **存储类服务**（PostgreSQL、garage S3、valkey/缓存、备份仓库）集中在 NAS，对外提供"数据原语"。
- **业务计算类服务**（Hermes 全家、AI Gate 应用层、Gitea UI、runner、浏览器池）无状态化，状态外置到 NAS 的数据原语。
- **软路由永不参与**以上任何一层，只做网络。

依据：两类服务的失效模式与维护节奏相反——存储类="活得越久越好别动它"（换盘/阵列/快照），业务类="反复重启是常态"（升级/回滚）。同机则后者连坐有状态数据。实证：gitea compose 栈的 watchtower 每日自动重启整个栈（含 gitea-postgres）。

限定条件：
1. "另一台设备"未必是新硬件——<host-01> 已充当会话/算力侧，缺的是边界纪律而非采购。
2. **冷热切分比业务/存储切分更细**：每轮同步读写的热路径优先就近；实测 <host-01>→NAS RTT avg 2.25ms（NetBird P2P host/host），对"人等它"的服务无感，对被 agent 循环放大的高频小查询须先基准验证。
3. 存储类内部仍需隔离介质敏感与协议敏感负载（garage 纠删码吃 CPU 会饿死同机 PG fsync），多原语共存时留 cgroup/VM 配额后手。
4. 副作用：所有业务新增"NAS 挂=全体降级"横向依赖，NAS 可靠性（阵列健康/UPS/备份演练）升为全站 P0。

## 二、共享 DB 选型（定案：B 的最小可行版）

- C（自建 DBaaS/控制面）排除：两人舰队养不起运维宠物；外购托管违背隐私红线。
- B（platform compose 栈）骨架，首批租户见第四节：
  ```
  /volume1/docker/platform/
  ├── docker-compose.yml   # postgres:16-alpine + valkey，端口仅绑 NB 网段(<lan-ip>)
  ├── init/00-users.sh     # 建库/用户脚本归 platform，不散落进应用栈
  └── backup → garage      # pg_dump 定时打 S3，备份责任上移
  ```
- 接口纪律（按 C 的契约写 B）：应用侧只见 DSN（scram），永不 mount 数据目录；凭据进 credential store 不进 compose 明文（gitea 现栈密码裸奔是反面教材）；platform 重启/升级=有公告维护窗口，禁止 watchtower 代劳。
- 存量不动：gitea-postgres、aigate、context_anchor 三个单消费者库不迁。

## 三、KB 定位考据（回答"共用记忆还是复用 PG"）

结论：**原始意图不是共用记忆**。证据链：
- Phase 2 Goal 原文（AGENTS.md，2026-08-23）："sink useful conversation facts into KB so cross-session recall uses semantic vector search instead of the weaker built-in SQLite FTS"——动机是替换我自己的弱检索。
- memory 插件 `kb_name`/`pg_dsn` 是 profile-scoped 配置（默认 astra-kb）——为多实例部署留口，非共享设计。
- constellation docs/12 §13.1 教义：真多智能体="多个独立大脑，互不读对方记忆"；记忆隔离是边界，共享记忆被明确判为设计混淆。
- 真正的共享发生在**工具层**（docs/03-tool-sharing.md，2026-08-10 起）：执行者经 aigate 门禁消费同一 KB MCP 端点，读的是策展库，带各自 API key。
- 跨 agent 记忆流的唯一合法形态=台账模式（§13.2.1/13.3）：显式写共享台账/全局 memory，A2A 消息不自动入记忆。

一句话：**共享的是图书馆（策展库），不是脑内记忆（mem 库）。**

## 四、公共策展库全景 + dynamic_ref 机制

| 库 | 装什么 | 写方（curate 流程） |
|---|---|---|
| hermes_config | 外挂服务/MCP/CLI/端口登记 | 部署即登记 |
| service_mgmt | 管理方案/健康检查/维护日志 | cron 巡检更新 |
| sre_incidents | 事故根因与修复复盘 | 事故后写；learn.py 月度模式扫描→建议新 skill |
| dynamic_ref | 易变常数（Gateway 消息长度限制、preference-query-map 路由表等） | 月度 cron 提醒 + 人工核对落库 |

dynamic_ref 三层实现：① 存储=普通 KB 库无特殊 schema；② 变更侦测=cron「astra-sre 月维护」(39112de7ccc7, `0 9 1 * *`) 跑 astra-sre-refresh.sh，比对 ~/.hermes 版本指纹，产出"请检查 Gateway 消息长度限制是否需更新"报告投递 Matrix home；③ 人审落库——脚本只提醒，确认新值+kb_update 由我判断执行（权威源是人读上游文档，无法机械 diff）。SOUL/hub 里只留指针不留值："完整参考文档 → kb_search("dynamic_ref", 关键词)"。

## 五、规范化终态与迁移行动清单（待桌面端执行）

1. NAS platform PG 立项，首批租户=四座策展库（读多写少、跨 agent、可容忍 2ms）。
2. 各 agent 的 mem_* 库随后迁入同一 PG：逻辑隔离靠库名+网关 ACL（执行者可读策展库、禁读彼此 mem 库）；物理上服从统一数据层原则——插件代码各机自装，`pg_dsn` 指过去。
3. 前置门槛：sink/search 延迟基准对比，不过关则 mem 库例外留守 <host-01> 并记 ADR。
4. KB MCP server (:3003) 与 embed 链路（aigate :20128）留在 <host-01>——无状态服务跟着最大热消费者走。
5. 认证收口：PG peer auth → TCP+scram（DSN 名沿用 registry.yaml 已预留的 ASTRA_KB_PG_DSN）；3003 直连收进 aigate 网关统一发 key。
6. 立约定：agent 各自 mem_<agent> 库命名 + 公共库 curate 流程写进 constellation AGENTS.md。
7. 顺带账（同日盘点遗留）：<host-01> 磁盘 85%（/nix GC 33G）、postgresql18 冗余包清理、NAS builder cache prune、cloudflare-cloudflared-1 Created 状态容器去留待用户确认。

## 六、当日已完成动作（2026-09-26）

- NAS 僵尸容器清理：删除 7 个 camofox CI 测试残留 + act_runner_nix_old061 + diun + minio + 4 个 Created 残留 + docviewer×2，释放 ~800M；保留名单核对无误删。
- runner 限额结论：act_runner_nix 管理容器无需限额（capacity=1 串行天然限流、常驻仅 11M）；若限额应加在 job 容器 options（--cpus/--memory），挂载现状干净无需清理。
