# Megolm `shared` 一次性标记的局限性与修复方案

> 2026-06-07 发现：网络中断重连后，Megolm 会话的 `shared=true` 标记不会被重置，导致密钥未重新分享给用户设备。

---

## 背景：Megolm 会话生命周期

Matrix E2EE 中，每个房间有一个 **outbound Megolm 会话**（负责加密发出的消息）：

```
创建会话 → 分享密钥（shared=1）→ 发送消息（msg_count++）→ 满 100 条后自动轮换
```

关键标记：
- `shared` — **一次性布尔值**，创建时 false，首次分享密钥后设为 true，之后不再重置
- `message_count` — 已使用次数，到 100 后自动建新会话

## 问题：为什么重连后密钥不会重新分享

### 时间线

```
正常状态:
  Gateway(shared=1, msgs=27) ───Megolm 密钥──→ User Device ✅

DNS 中断 (13:51~14:07):
  Gateway ──(? 同步断开 ?)── User Device

重连 (14:17):
  Gateway: "shared=1 → 密钥已分享过，直接用"
  Gateway: 发送新消息（无密钥分享） ← ❌
  User Device: "收到加密消息，但没收到过这个会话的密钥" → 🔒
```

### 根因

**mautrix-python 的 `shared` 字段是一个一次性的乐观标记。** 它只在创建会话时被设为 false，首次 `share_group_session()` 成功后设为 true。没有任何逻辑会在网络重连后重置它。

这意味着：
- 网络断连导致用户设备丢失了 Megolm 密钥
- Gateway 侧不知道用户丢过，以为 `shared` 就够了
- 消息照常加密发送，用户收得到但解不开

---

## 诊断方式：`(after key share)` 标记

Gateway 日志中，正常发送的消息带有标记：

```
2026-06-07 04:01:37 ... (after key share)  ← ✅ 密钥重新分享过
```

如果消息**没有**这个标记，说明 Gateway 复用了旧会话且没有重新分享密钥：

```
2026-06-07 14:17:31 ... (没有这个标记!)     ← ⚠️ 潜在问题点
```

**诊断步骤：**
```bash
# 检查最近的消息是否都有 key share 标记
grep "sent event.*to .*gloriosa.space" ~/.hermes/logs/gateway.log | tail -10

# 看其中有没有不带 "(after key share)" 的
grep "sent event.*to .*gloriosa.space" ~/.hermes/logs/gateway.log \
  | grep -v "after key share" | tail -5
```

---

## 关键发现 1：`add_outbound_group_session` vs `update_outbound_group_session`

**修脚本时踩的坑：** 修改 session 的 `shared` 属性后必须用 `add_outbound_group_session()`（UPSERT），因为 `update_outbound_group_session()` 的 SQL 只更新 `session`, `message_count`, `last_used` 三个字段：

```sql
-- update_outbound_group_session (shared 不更新!)
UPDATE crypto_megolm_outbound_session SET session=$1, message_count=$2, last_used=$3
WHERE room_id=$4 AND session_id=$5 AND account_id=$6

-- add_outbound_group_session (UPSERT，更新全部字段含 shared)
INSERT INTO crypto_megolm_outbound_session (...) VALUES (...)
ON CONFLICT (account_id, room_id) DO UPDATE SET session_id=excluded.session_id, shared=excluded.shared, ...
```

**修复方案：** 修改 `session.shared = False` 后，用 `add_outbound_group_session()`（UPSERT）保存，而不是 `update_outbound_group_session()`。

## 关键发现 2：`hermes gateway stop` → `start` 竞争条件

**症状：** Gateway 反复 连上 → 1 秒后断 → 日志无错误 → `_sync_loop` 崩溃 `AttributeError: 'NoneType' object has no attribute 'sync_store'`。

**根因：** `stop` 命令发 SIGTERM → `disconnect()` 设置 `self._client = None` → `_sync_loop` 任务晚一步才开始 → `client = self._client` 得到 `None` → 崩溃。

**预防：**
- `hermes gateway stop` 后等至少 5 秒再 `hermes gateway start`
- `_sync_loop` 首行加 `if client is None: return`（已纳入 004 补丁）

## 关键发现 3：方法定义缩进陷阱

**症状：** Gateway 日志一切正常但 `connect()` 返回 `None`（→ `✗ failed to connect`），无错误日志。
**根因：** 在 `connect()` 方法的代码中间插入了 `async def _deferred_reshare_rooms(self)`（4 空格缩进），Python 认为 `connect()`（8 空格缩进）在此结束。后续的 `try: return True` 实际属于新方法。

**修复：** 辅助方法定义必须放在包含方法的**末尾之后**，用 `grep -n "async def "` 确认所有方法在 4 空格对齐。
详见 `references/connect-indentation-bug.md`

---

## 修复方案对比

### A：重建 Megolm 会话（v2 — 旧脚本，已备份）

运行 `e2ee-repair-keys.py` v2（备份为 `.bak.20260607`）：
1. 调用 `crypto_store.remove_outbound_group_sessions(room_id)` → 删旧会话
2. 调用 `olm.share_group_session(room_id, users)` → 建新会话并分享

| ✅ 优势 | ⚠️ 代价 |
|:--------|:---------|
| 简单粗暴，肯定有效 | 旧会话删除 → 旧消息永久不可解密 |

### B：重新分享现有会话密钥（v3 — 推荐）

运行当前 `e2ee-repair-keys.py`（v3）：
1. `session = crypto_store.get_outbound_group_session(room_id)` → 获取现有会话
2. `session.shared = False; session.users_shared_with = set()` → 重置标记
3. **必须用 `add_outbound_group_session()`**（UPSERT，写 full 字段），而不是 `update_outbound_group_session()`（后者不写 `shared` 字段！）
4. `olm.share_group_session(room_id, users)` → 看到 `shared=False` → 分享现有会话密钥

| ✅ 优势 | ⚠️ 代价 |
|:--------|:---------|
| 保留旧会话 | 需要手动触发 |
| 旧消息可恢复（Request keys） | |

### C：mautrix SDK 补丁 + Gateway 自动修复（004 — 终极方案）

**两个补丁一起组成完整预防链：**

| 补丁 | 文件 | 作用 | 依赖 |
|:----|:----|:----|:----|
| 003 | `mautrix/crypto/encrypt_megolm.py` | 新增 `reset_outbound_session_sharing()` SDK 方法 | 无 |
| 004 | `gateway/platforms/matrix.py` | Gateway 重连后自动恢复 E2EE（含 None client guard） | 依赖 003 |

**004 补丁的工作原理：** 在 Gateway 的 `connect()` 方法中（初始 sync 完成后），分两步修复：

**第一步（立即，connect 时执行）：** 遍历所有房间，重置并重新分享 Megolm 会话密钥。

**第二步（延迟 30 秒后执行 — 针对时序问题）：** 启动 `_deferred_reshare_rooms()` 后台任务，30 秒后再次对所有会话重新分享密钥。此时设备列表应已同步。日志：`deferred re-share complete for N room(s)`

**验证方法：** Gateway 日志中出现以下标记：
```
Matrix: connected              ← connect() 成功
✓ matrix connected             ← Gateway 接受了连接
Matrix: deferred re-share complete for 3 room(s)  ← 自动修复
```

### D：定时 cron（不推荐）

每 N 小时跑一次 `e2ee-repair-keys.py` 强制重分享所有会话。不推荐。

---

## 补丁库结构

所有补丁已统一编号管理在 `~/.hermes/patches/`，详见 README.md。

升级后恢复（按顺序）：
```bash
# 1. Hermes 源码补丁 (git format — git apply)
cd ~/.hermes/hermes-agent
git apply patches/001-skin-auto.patch
git apply patches/002-e2ee-ipc.patch
git apply patches/004-gateway-e2ee-autoheal.patch

# 2. mautrix SDK 补丁 (unified diff — patch 命令!)
cd ~/.hermes/hermes-agent/venv/lib/python3.11/site-packages
patch -N -p1 < ~/.hermes/patches/003-mautrix-reset-shared.patch
```

> **⚠️ 003 是 unified diff 格式（`patch -p1`），不是 git format！** 不要用 `git apply`。

## 相关资源

- `~/.hermes/scripts/e2ee-repair-keys.py` — 密钥重分享脚本 v3（保留旧会话；旧版备份为 `.bak.20260607`）
- `~/.hermes/patches/` — 补丁库，004 含 Gateway 自动修复
- `astra-sre-fix-e2ee` skill — E2EE 故障诊断与修复总入口
- `references/connect-indentation-bug.md` — Python 方法定义缩进陷阱详解
