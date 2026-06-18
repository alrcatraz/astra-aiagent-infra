---
name: astra-sre-fix-e2ee
description: "E2EE 故障诊断与修复 — Stale OTK、跨签名丢失、同步循环卡死、设备 ID 复用缓存冲突"
version: 3.11.0
author: ANGELIA
platforms: [linux]
level: L2/L3
related_skills:
  - server-restart-recovery
  - full-e2ee-recovery-after-server-rebuild
  - astra-sre-restart-service
---

# astra-sre-fix-e2ee — E2EE 修复子 skill

> 当 Hermes Gateway 的 Matrix E2EE 出问题时加载此 skill。
> 配合 sre_incidents 知识库中的 "E2EE Stale OTK 修复" 使用。
>
> 📌 2026-06-18 v3.11.0 更新：
>   - 修正：`e2ee-watchdog.sh` 并非退役——旧版 Gateway 子进程看门狗已退役，但替换为 Hermes cronjob（no_agent=true）格式的看门狗持续运行中，每分钟检测 E2EE 状态
>   - 新增陷阱：`share_keys()` 在 startup 时被调用两轮（`_verify_device_keys_on_server` 第一轮上传 device keys + OTKs，第二轮无料可干）→ 产生一次性良性 "No one-time keys" 警告
>   - 新增陷阱：`KillMode=mixed` + cron 看门狗的修复脚本竞争条件
>
> 📌 2026-06-18 v3.10.0 更新：新增诊断第十一步（本机 OTK 生成失效区分 — claim/upload API 对比验证）、第十二步（`.e2ee-repairing` 残留锁检测）；陷阱表新增残留锁条目；细化「零出站会话时 No one-time keys 警告无害」条目加入本地生成失效例外（设备运行 24h+ 时）。

> 📌 2026-06-11 v3.9.0 更新：退役 e2ee-watchdog.sh（已清理，见陷阱表）；新增 e2ee-repair.py 硬编码凭证风险提醒；
>    补充触发条件：Gateway 自身重启（非整机）也可导致 identity key 漂移 → stale OTK。
>
> 📌 **Phase 3 修复等级设计已定稿。** 本 skill 的修复步骤将在后续迭代中按 L1/L2/L3 分级（L1: 自动执行, L2: 自动+通知, L3: 需你确认）。
> 设计文档: `~/Projects/astra/astra-sre/references/phase3-design.md`
>
> 📌 2026-06-07 v3.5.0 更新：🔴 设备 ID 复用诊断条目新增完整修复指引 — Variant A + 全新 device ID 无需用户操作；
>    陷阱表条目同步更新；`device-id-reuse-unknown-device.md` 方案重构（A/B/C/D），
>    明确 Variant A 保留跨签名时 recovery key 自动完成设备信任。
>
> 📌 2026-06-10 v3.8.0 更新：修复 `_on_encrypted_fallback` 代码示例中的 `client.mxid` → `client.mxid` 笔误（实际 bug 导致 2,500+ 次静默崩溃，阻断密钥自动修复路径）；新增诊断第十一步检查 errors.log 中的 AttributeError 崩溃模式；新增陷阱条目「`_on_encrypted_fallback` 静默崩溃」。
>    第十步 sync 错误频率检查（E2EE 重建后必查）、
>    `references/sync-timeout-post-rebuild.md` 完整诊断/修复参考文档。
>
> 📌 2026-06-07 v3.4.0 更新：用户侧信任问题关键发现、
>    Element 没有 "Request keys" 按钮（用户实测更正）、
>    跨签名验证≠设备信任区分、非对称加密现象说明、
>    密钥请求被用户 Element 拒绝的机制 (`allow_key_share` / `resolve_trust`)、
>    `systemctl --user restart` 的正确用法。
> 📌 2026-06-07 v3.3.0 更新：加入「DecryptionDispatcher 缺失」根因、
>    手动密钥请求脚本(e2ee-request-keys.py)、入站会话来源诊断、
>    crypto_account.sync_token 为空陷阱。
> 📌 2026-06-07 v3.2.0 更新：加入「零出站会话」实战发现、
>    解决 crypto.db 清空后无法解密问题、`No one-time keys` 无害警告说明。
> 📌 2026-06-07 v3.1.0 更新：加入 004 补丁（deferred auto-heal）、
>    indentation bug 陷阱、sync loop None guard、stop/start 竞争条件。
> ⚠️ 关键安全警告：不要用外部脚本修复正在运行的 Gateway！
>    修复脚本创建第二个 Matrix 客户端同时操作 crypto.db 会导致冲突。
>    e2ee-request-keys.py 例外：它使用 REST API 而不是创建第二个 Matrix 客户端。

---

## 触发条件

- Gateway 显示 active 但 Element 上 bot 离线
- 日志中出现 "stale one-time keys" 或 "OTK"
- Gateway 同步循环卡死（不停 sync → fail → retry）
- Matrix 消息显示 "无法解密"（unable to decrypt）
- Gateway 网络中断后重连（日志中先出现 `sync error` 后出现 `using access token`）
- 日志中出现 `created fresh Megolm session for` 或 `re-shared Megolm session for`
- `deferred re-share complete` 未出现（auto-heal 时序问题）
- `e2ee-repair-keys.py` 运行时显示 `无出站会话` — 说明 crypto.db 被清空或设备重置，Gateway 还没有任何 Megolm 加密通道
- **Gateway 连接正常但收不到任何入站消息** — sync 循环在运行，TCP 连接 ESTAB，但入站消息全丢
- **Element 上看到 '无法解密' 但 Gateway 日志无任何 decrypt 错误** — 说明加密事件根本没被处理，而非解密失败
- **🔄 服务器重启后！** — 即使 crypto.db 在持久化存储上 (/home) 完整保留，E2EE watchdog 子进程可能在重启前用同一 device ID 重建了 crypto.db → 服务端 OTK 签名与新的 identity key 不匹配 → stale OTK。**重启后必查项：** `journalctl --user -u hermes-gateway --no-pager -n 50 | grep "stale one-time keys"`
  ⚠️ **注意：不仅是整机重启。** Gateway 自身意外重启（崩溃后 systemd Restart=always 拉起、或者 `systemctl --user restart`）也可能触发 identity key 变更。June 10 案例：Gateway 在 31 分钟内重启两次后 identity key 漂移，11 日整机重启时才暴露。**Gateway 重启后也应检查 stale OTK。**
- **👀 bot 能发消息、你能收到，但你回复的消息 bot 收不到** — 非对称加密问题：outbound session 正常但无 inbound session。这是 DecryptionDispatcher 缺失 + 用户设备不信任 bot 新设备的典型表现。常见于 crypto.db 清空后用**同一设备 ID** 重建的场景。见 `references/device-id-reuse-unknown-device.md`
- **🐢 Gateway 回复延迟明显增加** — 从你发消息到看到已读回应的时间显著变长。日志中 sync error 以 ~70 秒间隔规律出现，错误信息为空字符串，且 Nginx/Synapse 配置均正常。这是 E2EE 重建后网络路径被暴露出的问题——sync 长连接通过 Cloudflare 时 ~50% 会 TCP 半挂，直到 asyncio.wait_for(timeout=45.0) 超时。排查方法见 references/sync-timeout-post-rebuild.md
- **Element 显示"由未知或已被删除的设备加密"** — 用户设备不信任 bot 的新加密身份（跨签名后设备密钥变了，但用户侧未同步信任）
- **🔴 Element DM 房间 bot 显示 "已验证" 但消息仍显示 "由未知设备加密"** — 关键矛盾信号！跨签名验证通过（服务器侧）但用户 Element 有旧 identity key 缓存（客户端侧），两者独立判断。**根因：crypto.db 清空后同一设备 ID 被复用。**
  **修复：** 走 `full-e2ee-recovery-after-server-rebuild` 的 **Variant A**（新 device ID + 保留 recovery key）。启动后 `cross-signing verified via recovery key`，**无需用户任何操作**，所有客户端自动信任新设备。


---

## 诊断流程

### 第一步：确认 Gateway 实际状态

```bash
systemctl --user is-active hermes-gateway
tail -100 ~/.hermes/logs/gateway.log | grep -E "error|Error|OTK|stale|token|401|decrypt"
```

### 第二步：确认 Synapse 可达

```bash
curl -s "http://localhost:8008/_matrix/client/versions" | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('Synapse OK' if 'versions' in d else 'FAIL')"
```

### 第三步：零冲突诊断 — 直接读 crypto.db（推荐）

```bash
python3 ~/.hermes/skills/sre/astra-sre-fix-e2ee/scripts/check-crypto-state.py
```

输出示例：
```
=== Outbound Megolm Sessions ===
  DM    session=qpOWex8ovc2UJeD9w... shared=1 msgs=1/100 age=120s
  Home  session=0+dTznIMRVJtXGPEu... shared=1 msgs=0/100 age=121s

=== Inbound Megolm Sessions ===
  Total: 55

=== Account ===
  device_id=hermes-bot-v1780662000, account.shared=True
```

- `shared=1` 但用户仍无法解密 → 密钥标记但未送达设备（时序问题，需 deferred re-share）
- **无 outbound session** → crypto.db 被清空或设备重置！**不等第一次发消息**，立即运行 `e2ee-repair-keys.py` 主动创建新会话
- `session.shared=False` → Gateway 的 auto-heal 已经重置了标记（正常）
- 有 outbound session 但 `shared=1` 且用户仍无法解密 → 密钥标记但设备列表未同步（时序问题，需要 deferred re-share）

### 第四步：检查 `(after key share)` 标记

```bash
grep "sent event.*to .*gloriosa.space" ~/.hermes/logs/gateway.log | tail -10
grep "sent event.*to .*gloriosa.space" ~/.hermes/logs/gateway.log \
  | grep -v "after key share" | tail -5
```

正常消息带 `(after key share)` 标记。不带标记意味着 Gateway 复用了旧 Megolm 会话且未重新分享密钥。

### 第五步：检查是否发生过重连

```bash
grep -n "sync error\\|using access token.*device" ~/.hermes/logs/gateway.log | tail -20
```

如果 "sync error" 后出现 "using access token"，说明发生了重连事件。

### 第六步：检查 `_sync_loop` 是否因 None client 崩溃

```bash
journalctl --user -u hermes-gateway --since "5 minutes ago" --no-pager 2>/dev/null \
  | grep -i "AttributeError\\|NoneType.*sync_store\\|Traceback"
```

如果找到 traceback，说明 disconnect() 在 sync_loop 启动前设置了 `self._client = None`（竞争条件）。已纳入 004 补丁修复。

### 第七步：检查入站 Megolm 会话的来源

**新增 v3.3.0 — 关键诊断步骤！** Crypto.db 有入站会话但都是 bot 自己的密钥 → 用户的加密消息从未被解密过。

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('/home/alrcatraz/.hermes/platforms/matrix/store/crypto.db')
cur = db.execute('SELECT sender_key, room_id, session_id, received_at FROM crypto_megolm_inbound_session ORDER BY received_at DESC')
for row in cur.fetchall():
    is_bot = 'obTdrkw8rWz' in str(row[0])  # bot 的 identity key 前缀
    print(f'  [{\"BOT\" if is_bot else \"!! USER !!\"}] key={str(row[0])[:30]} room={str(row[1])[:30]} recv={row[3]}')
db.close()
"
```

- 全部 `[BOT]` → **没有任何用户设备的入站会话** → 说明 DecryptionDispatcher 缺失或解密失败未处理
- 有 `[!! USER !!]` → 入站会话存在，但可能因其他原因未被使用

### 第八步：检查 DecryptionDispatcher 注册状态

```bash
grep -n "DecryptionDispatcher\|add_dispatcher" ~/.hermes/hermes-agent/gateway/platforms/matrix.py
```

输出应有 `add_dispatcher(DecryptionDispatcher)`。如果只有 `MembershipEventDispatcher` → **这就是根因**。

### 第九步：检查 crypto_account.sync_token

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('/home/alrcatraz/.hermes/platforms/matrix/store/crypto.db')
cur = db.execute('SELECT sync_token FROM crypto_account LIMIT 1')
token = cur.fetchone()
print(f'sync_token exists: {bool(token[0]) if token else False}')
db.close()
"
```

- `False`（空字符串）→ 可能影响 to-device 消息同步和密钥交换

### 第十步：检查 sync 错误频率（E2EE 重建后必查）

E2EE 全量重建后，新设备的 sync 行为可能暴露网络路径的不稳定性。在诊断延迟问题时优先执行此步：

```bash
# 1. 按日统计 sync 错误数量
grep "sync error" ~/.hermes/logs/gateway.log | sed 's/,.*//' | sed 's/ .*//' | sort | uniq -c | sort -k2

# 2. 正常基线：< 20/天；E2EE 重建后异常：400-660/天
# 3. 错误信息为空字符串 → asyncio.wait_for 超时 → 网络路径问题
```

如果错误率异常高，参考 `references/sync-timeout-post-rebuild.md` 排查。

### 第十一步：检查本机 OTK 生成是否失效（v3.10.0 新增）

**关键诊断区分：** "No one-time keys" 警告有两种完全不同的根因。

**场景 A — 服务器 OTK 耗尽（正常使用后被消耗）：** OTK 被正常占用，等待 `handle_otk_count` 自动触发补充。

**场景 B — 本地 OlmAccount OTK 生成失效（需修复）：** 本地 `get_one_time_keys()` 返回空，`share_keys` 永远失败。

```bash
# 诊断：先用 claim 检查服务器是否真有 OTK
TOKEN=$(grep '^MATRIX_ACCESS_TOKEN=' ~/.hermes/.env | cut -d= -f2)
DEVICE=$(grep '^MATRIX_DEVICE_ID=' ~/.hermes/.env | cut -d= -f2)
curl -s --max-time 10 -H "Authorization: Bearer $TOKEN" \
  -X POST -d '{"one_time_keys":{"@hermes00:matrix.gloriosa.space":{"'$DEVICE'":"signed_curve25519"}}}' \
  'https://matrix.gloriosa.space/_matrix/client/v3/keys/claim' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); otks=d.get('one_time_keys',{}).get('@hermes00:matrix.gloriosa.space',{}).get('$DEVICE',{}); print(f'OTKs on server: {len(otks)} keys claimed')"

# 然后用 upload (no-body) 检查服务器报告的 count
curl -s --max-time 10 -H "Authorization: Bearer $TOKEN" -X POST \
  'https://matrix.gloriosa.space/_matrix/client/v3/keys/upload' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Server OTK count:', d.get('one_time_key_counts', {}))"
```

- **claim 成功 + server count > 0** → 场景 A（正常波动，等待下次 sync 自动补充）
- **claim 返回空 + server count = 0** → 场景 B — **本地 OlmAccount OTK 生成失效**。设备运行过长（24h+）后 OlmAccount 状态损坏，`account.get_one_time_keys()` in `mautrix/crypto/machine.py` 调用 `generate_one_time_keys()` 返回空列表。**修复：全量 Variant A（新 token + 新 device_id + 清 crypto.db）。**

**代码路径（供参考）：**
```
mautrix/crypto/machine.py:_share_keys()
  → account.get_one_time_keys(user_id, device_id, current_otk_count)   [account.py:93]
    → new_count = max_one_time_keys // 2 - current_otk_count
    → generate_one_time_keys(new_count)
    → returns self.one_time_keys.get("curve25519", {})  ← 可能返回空字典
  → if not device_keys and not one_time_keys:
      → "No one-time keys nor device keys got when trying to share keys"  ← 你看到的警告
```

### 第十二步：检查 `.e2ee-repairing` 锁文件是否残留（v3.10.0 新增）

看门狗脚本（`e2ee-watchdog.sh`）使用 `.e2ee-repairing` 锁文件防止修复冲突。如果修复被中断（SSH 超时、kill、重启），锁文件会残留。

```bash
stat ~/.hermes/scripts/.e2ee-repairing
```

- 文件存在且 modification time 超过 10 分钟 → **残留锁**
- 后果：看门狗每分钟检测到问题 → 发现锁存在 → 跳过修复 → 仍 exit 1 → 用户每分钟收到失败通知

**修复：**
```bash
rm -f ~/.hermes/scripts/.e2ee-repairing
```

清除后，下个看门狗周期即可自动触发修复。如果不想等，手动运行：
```bash
~/.hermes/scripts/e2ee-repair.py
```

> **注意：** `e2ee-repair.py` 创建第二个 Matrix 客户端操作同一 crypto.db，有冲突风险。但零出站会话场景下冲突风险较低。

### 第十三步：检查 `_on_encrypted_fallback` handler 崩溃（v3.8.0 新增）

这是最容易被忽略的根因之一。`_on_encrypted_fallback` handler 在 `DecryptionDispatcher` 解密失败时负责自动请求 Megolm 密钥。如果它静默崩溃，密钥请求永不发出→用户侧显示"无法解密"但 Gateway 日志无 decrypt 错误。

```bash
# 统计静默崩溃次数
grep -c "has no attribute 'user_id'" ~/.hermes/logs/errors.log

# 查看最新实例
grep "has no attribute 'user_id'" ~/.hermes/logs/errors.log | tail -3
```

- **崩溃次数 > 0** → `_on_encrypted_fallback` handler 从未正常工作过。每次解密失败触发了这个 handler 但直接炸掉，自动密钥恢复路径断裂。
- 崩溃路径：`matrix.py:1003` → `getattr(event, 'sender', None) == client.mxid` → `AttributeError: 'Client' object has no attribute 'user_id'`
- **修复**：将 `client.mxid` 改为 `client.mxid`（整个代码库一致使用 `client.mxid`，第 1003 行为孤立笔误）。修改后需重启 Gateway 生效。

---

## 修复步骤

### A. [L3] 完全恢复（Stale OTK / 跨签名损坏）
> 🔴 涉及 DB 修改、token 轮换、crypto.db 删除，必须你确认

使用 `full-e2ee-recovery-after-server-rebuild` skill 的流程。

### B. [L2] 重新共享密钥（消息显示无法解密）
> 🟡 自动执行 + 事后通知

运行：`~/.hermes/scripts/e2ee-repair-keys.py`

**两种情况都适用：**

| 场景 | 脚本行为 | 适用场景 |
|:----|:---------|:---------|
| 🟢 有出站会话但 shared=0 | 重置 shared 标记后重新分享密钥 | 网络中断后重连，旧会话存在 |
| 🟢 **无出站会话** | **创建全新的 Megolm 会话并分享密钥** | crypto.db 清空、设备重置、全新部署 |

> 💡 **"无出站会话"是最容易被忽略的情况。** 此时窃以为"等 Gateway 第一次发消息会自动创建" → 但用户侧已经看到了"无法解密"的历史消息，被动等待不能修复已出现的问题。**主动运行此脚本立即创建新会话。**

> ✅ **v3 改进：保留旧的 outbound Megolm 会话**，仅重置 `shared` 标记后重新分享密钥。
>    旧消息仍可通过 Element 上点 🔒 → Request keys 恢复解密。
> 📦 旧版脚本备份为 `e2ee-repair-keys.py.bak.20260607`
>
> ⚠️ **关键冲突警告：** 此脚本创建第二个 Matrix 客户端，与运行中 Gateway 竞争操作同一 crypto.db。
>    脚本的 `client.sync()` 可能触发事件处理删除 Gateway 的出站会话。
> **优先用 004 补丁的 Gateway 自修复，不要只靠外部脚本。**
>
> 在零出站会话场景下，冲突风险较低（没有旧会话可以被误删）。推荐在 Gateway 运行状态下直接执行。

### D. [L2] 手动请求密钥（DecryptionDispatcher 缺失时的应急方案）
> 🟡 使用 REST API 不冲突，自动执行 + 事后通知

**v3.3.0 新增 — 当 Gateway 有出站会话但入站消息全丢时使用。**

`~/.hermes/scripts/e2ee-request-keys.py` — 通过 Matrix REST API 直接发送 `m.room_key_request`，**不创建第二个 Matrix 客户端，不与 crypto.db 冲突**。

```bash
cd ~/.hermes && source hermes-agent/venv/bin/activate
python3 scripts/e2ee-request-keys.py
```

脚本逻辑：
1. 查询 DM 房间最近的加密事件（`/messages?dir=b&limit=5`）
2. 提取来自 @nanaly 的 `sender_key` 和 `session_id`
3. 通过 `PUT /_matrix/client/v3/sendToDevice/m.room_key_request/{txnId}` 发送密钥请求
4. 同时发送给用户的所有设备（fallback 策略）

> **工作原理：** 此脚本使用 Matrix Client-Server REST API，与运行中的 Gateway 完全独立。发送的是标准的 `m.room_key_request` to-device 消息，用户设备收到后自动响应。

**触发后的预期行为：**
1. 用户设备收到密钥请求 → 通过已建立的 Olm 会话发送 `m.room_key`
2. Gateway 的 OlmMachine 在 sync 中收到 `m.room.encrypted` to-device 消息
3. 解密后提取 Megolm 会话密钥 → 添加到 `crypto_megolm_inbound_session`
4. **新消息**可被解密（旧消息已错过 sync 窗口，不可恢复）

> ⚠️ **⚠️ 重要陷阱：密钥请求可能被用户 Element 静默拒绝！**
>
> **用户 Element 的 `handle_room_key_request` 执行 `allow_key_share` 检查：**
> - 如果 bot 设备在用户端的信任等级低于 `share_keys_min_trust` → 抛出 `RejectKeyShare(code=UNVERIFIED)` → 密钥请求被拒绝
> - 用户 Element 上会显示 "由未知或已被删除的设备加密" — 这就是拒绝信号
>
> **解决方案：** 用户需要手动信任 bot 设备：
> 1. 在 Element 中：头像 → **设置 → 会话（Sessions）**
> 2. 找到 `hermes-bot-v1780662000`
> 3. 点击 **验证 / 信任此会话**
> 4. 验证后再次运行 `e2ee-request-keys.py`
>
> **关键发现：** ❌ Element **没有** "Request keys" 按钮（用户实测确认）。用户无法从 Element UI 手动请求 bot 的密钥——只能通过信任 bot 设备后让 Element 自动分享。

### E. 补丁 DecryptionDispatcher + 解密失败密钥请求（根本修复）

**v3.3.0 新增 — 根治此问题的代码级修复。**

在 `gateway/platforms/matrix.py` 的 `connect()` 方法中：

```python
from mautrix.client.encryption_manager import DecryptionDispatcher

# 在 MembershipEventDispatcher 同一行后添加
client.add_dispatcher(MembershipEventDispatcher)
client.add_dispatcher(DecryptionDispatcher)  # ← 新增
```

**额外还需要**：`DecryptionDispatcher.handle()` 在 `DecryptionError` 时不会自动请求密钥。需要自定义 handler 或补丁：

```python
# 在 _on_room_message 之外，注册 ROOM_ENCRYPTED handler 来处理解密失败
client.add_event_handler(EventType.ROOM_ENCRYPTED, self._on_undecryptable)

async def _on_undecryptable(self, evt):
    """当加密事件无法解密时，请求密钥"""
    try:
        from mautrix.client.encryption_manager import DecryptionDispatcher
        dd = DecryptionDispatcher(client)
        await dd.handle(evt)
    except DecryptionError as e:
        # 解密失败 → 请求密钥
        content = evt.content
        await client.crypto.request_room_key(
            room_id=evt.room_id,
            sender_key=content.sender_key,
            session_id=content.session_id,
            from_devices={evt.sender: [evt.content.device_id]},
            timeout=30,
        )
```

> ⚠️ 此修复需要 Gateway 重启生效。

**v3.3.1 更新 — 新增 `_on_encrypted_fallback` 处理器：**

即使注册 `DecryptionDispatcher`，mautrix 默认实现不会自动请求密钥。需要额外注册一个 `ROOM_ENCRYPTED` event handler 来捕获解密失败的加密事件并发送 key request。

已应用于 Gateway 代码 `gateway/platforms/matrix.py` 的 `connect()` 方法中：

```python
from mautrix.client.encryption_manager import DecryptionDispatcher
from mautrix.errors import DecryptionError
from mautrix.util import background_task

client.add_dispatcher(DecryptionDispatcher)

async def _on_encrypted_fallback(event):
    """Request Megolm session keys for undecryptable room events."""
    olm = getattr(client, 'crypto', None)
    if not olm:
        return
    if getattr(event, 'sender', None) == client.mxid:
        return
    try:
        await olm.decrypt_megolm_event(event)
        decrypted = await olm.decrypt_megolm_event(event)
        client.dispatch_event(decrypted, getattr(event, 'source', None))
        return
    except DecryptionError:
        pass  # Expected — decryption failed
    except Exception:
        pass

    content = getattr(event, 'content', None)
    if not content:
        return
    sender_key = getattr(content, 'sender_key', None)
    session_id = getattr(content, 'session_id', None)
    if not all([sender_key, session_id, getattr(event, 'room_id', None), getattr(event, 'sender', None)]):
        return

    logger.warning(
        "E2EE: requesting room key for %s from %s (session=%s...)",
        event.event_id, event.sender, session_id[:20],
    )
    try:
        devices = await olm.crypto_store.get_devices(event.sender)
        from_devices = {event.sender: list(devices.keys())}
    except Exception:
        from_devices = {event.sender: []}

    if from_devices.get(event.sender):
        background_task.create(
            olm.request_room_key(
                event.room_id, sender_key, session_id, from_devices, timeout=0,
            )
        )

client.add_event_handler(EventType.ROOM_ENCRYPTED, _on_encrypted_fallback)
```

> 注意：`timeout=0` 表示 fire-and-forget — 不等待响应，密钥异步到达。如果在 Gateway 模式下使用，需在 TUI/CLI 中执行重启。

两个补丁一起工作：003（mautrix SDK 方法）+ 004（Gateway 钩子）。

**不需要手动运行任何脚本。** Gateway 每次重连后自动为所有已加入的房间修复：

**第一步（立即，connect 时执行）：** 遍历所有房间，重置 shared 标记并重新分享密钥。

**第二步（延迟 30 秒后执行 — 针对时序问题）：** `_deferred_reshare_rooms()` 后台任务 30 秒后再次对所有会话重新分享密钥。此时设备列表应已同步。

**升级后恢复：**
```bash
# 顺序！004 依赖 003
cd ~/.hermes/hermes-agent
git apply patches/004-gateway-e2ee-autoheal.patch
cd ~/.hermes/hermes-agent/venv/lib/python3.11/site-packages
patch -N -p1 < ~/.hermes/patches/003-mautrix-reset-shared.patch
```

---

## 根因分析

### 网络中断后 "无法解密" 的机制

Matrix E2EE 的 Megolm 会话有一个 **一次性 `shared` 标记**——创建会话时首次分享密钥后设为 true，**永不重置**。当 Gateway 网络中断后重连，Gateway 检查 old outbound session → `shared=1` → "密钥已分享，不用再发" → 直接发加密消息但用户侧丢了密钥 → 🔒。

详见 `references/megolm-shared-once-limitation.md`

### `add_outbound_group_session` vs `update_outbound_group_session`

修脚本时必须用 `add()`（UPSERT），因为 `update()` 的 SQL 不更新 `shared` 字段。

详见 `references/megolm-shared-once-limitation.md#关键发现-1`

### DecryptionDispatcher 缺失 → 加密事件被静默丢弃（v3.3.0 新增）

**这是最隐蔽的根因之一。** 当 crypto.db 被清空重建后，Gateway 可能看起来完全正常（✓ connected、能发消息），但所有入站加密消息都被静默丢弃。

**事件链路：**

```
@nanaly 发消息 (m.room.encrypted)
  → sync_loop 收到 sync_data
  → client.handle_sync(sync_data) 分发事件
  → dispatch_event() 按 EventType 找 handler
  → ❌ 无人注册 EventType.ROOM_ENCRYPTED
  → 事件被 dispatch_event() 返回的空列表忽略 → 静默丢弃!
```

**代码证据：**

```python
# gateway/platforms/matrix.py ~line 978-987
client.add_dispatcher(MembershipEventDispatcher)          # ← 有
# (DecryptionDispatcher 被跳过了)
client.add_event_handler(EventType.ROOM_MESSAGE, ...)     # ← 有
```

即使注册 `DecryptionDispatcher`，mautrix 的默认实现（`encryption_manager.py:179-187`）在解密失败时只 log warning 并 return——**不会自动发送 key request**。

详见 `references/decryption-dispatcher-missing.md`

### crypto_account.sync_token 为空（v3.3.0 新增）

crypto.db 清空重建后，`crypto_account` 表的 `sync_token` 字段为 `''`（空字符串）。这可能导致 mautrix OlmMachine 的 to-device 消息同步异常。正常运行时此 token 应为一个 base64 字符串。

目前观察到此现象但未确认是否为直接致因。

### Gateway 重连循环的竞争条件（重要！）

```text
stop → SIGTERM → disconnect() → self._client = None
         → _sync_loop 才开始跑 → client = None → 崩溃
         → systemd 自动重启 → 循环
```

**修复（004 补丁内）：** `_sync_loop` 加入 `if client is None: return`。

### 方法定义缩进陷阱（2026-06-07 新增）

在 `connect()` 方法中间插入 `async def _deferred_reshare_rooms`（4 空格），Python 认为 `connect()`（8 空格）在此结束，后续代码属于新方法。`connect()` 返回 `None` → `✗ failed to connect`。

详见 `references/connect-indentation-bug.md`

---

## 已知陷阱

| 陷阱 | 说明 |
|:----|:------|
| `systemctl --user` hang | 用 `pkill -9 -f "hermes_cli.main gateway"` 绕过 |
| 设备 ID 必须全新 | 不要复用旧的（OTK 哈希冲突） |
| recovery key 只能用户创建 | 必须通过 Element Web |
| 旧消息可恢复 | Key re-share v3 保留旧会话 → 旧消息可 Request keys |
| **🚨 `share_keys()` startup 两轮调用 → 一次性良性警告（v3.11.0 新增）** | Gateway 启动时 `share_keys()` 被调用两次：<br><br>**第一轮：** 在 `_verify_device_keys_on_server()` 内（`matrix.py:667`）。新设备找不到服务器上的 device keys → 设 `shared=False` → 调用 `share_keys()` → 上传 device keys + 50 个 OTK → `shared=True` + `mark_keys_as_published()`。<br><br>**第二轮：** 紧随其后（`matrix.py:887`）。此时 `shared=True` 故 `device_keys=None`；`mark_keys_as_published()` 已清空本地 OTK 缓存 → `get_one_time_keys(50)` 返回空 → **"No one-time keys nor device keys got when trying to share keys"**。<br><br>此警告**绝对良性**：服务器已有 50 个 OTK，后续 `handle_otk_count` 会在消耗到 < 50 时自动补充。**诊断：** 仅启动时出现 1-2 次，之后不再出现 = 良性。持续出现 100+ 次 = 场景 B（本地 OTK 生成失效）。<br><br>**注意：** 如果启动了 `--replace` 模式（Gateway 热重启），日志中的第一轮 `_verify_device_keys_on_server` 可能被跳过（server 已有 device keys），两轮调用合并为一轮。此时完全不见此警告。|
| 重启切断当前会话 | 如果通过 Gateway 通信，重启会中断对话 |
| **🚨 脚本与 Gateway 冲突** | 修复脚本创建第二个 Matrix 客户端，`client.sync()` 可能触发事件处理删除 Gateway 的出站会话。**零出站会话场景下冲突风险较低**（没有旧会话可被误删） |
| **🚨 e2ee-watchdog.sh（cron 版活跃中）** | 看门狗经历了两代架构：<br><br>**第一代（已退役）：** 作为 Gateway 子进程运行。检测到 stale OTK 后调用 `e2ee-repair.py` 自动修复 → 修复脚本创建第二个 Matrix 客户端同时操作 crypto.db → 可能重新创建 crypto.db（同一 device ID + 新 identity key）→ **使 stale OTK 问题恶化**。2026-06-11 清理。<br><br>**第二代（当前活跃）：** Hermes cronjob（no_agent=true），每 1 分钟执行 `~/.hermes/scripts/e2ee-watchdog.sh`。不再作为 Gateway 子进程运行 → 无 crypto.db 竞争风险。逻辑：检测多类 E2EE 故障（access token 失效、stale OTK、大量解密失败、大量 "No one-time keys" 警告）→ 触发 `e2ee-repair.py` 全量修复。<br><br>**陷阱：`KillMode=mixed` 竞争条件（v3.11.0）：** Gateway 的 systemd unit 使用 `KillMode=mixed`。当看门狗的修复脚本 (`e2ee-repair.py`) 调用 `systemctl stop hermes-gateway` 时，Systemd 发送 SIGTERM（后 SIGKILL）给 gateway cgroup 中的所有进程。如果修复脚本的子进程（SSH、systemctl start）恰好落在同一 cgroup 中 → 被一并杀死 → gateway 起不来 + `.e2ee-repairing` 锁残留。**绕过：** 手动按 Variant A 修复前暂停看门狗（`cronjob action=pause job_id=<id>`），修复完再恢复。|
| **🚨 `.e2ee-repairing` 锁文件残留** | 看门狗（cronjob no_agent 模式运行的 `e2ee-watchdog.sh`）使用 `~/.hermes/scripts/.e2ee-repairing` 锁文件防冲突。如果修复被中断（SSH 超时、kill、Gateway 重启），锁文件残留 → 看门狗每次检测到问题 → 锁存在 → 跳过修复 → 仍 `exit 1` → 用户每分钟收到失败通知。**诊断：** `stat ~/.hermes/scripts/.e2ee-repairing`，modify time > 10 min = 残留。**修复：** `rm -f ~/.hermes/scripts/.e2ee-repairing`。见诊断第十二步。 |
| **🚨 e2ee-repair.py 含硬编码凭证** | `~/.hermes/scripts/e2ee-repair.py` 明文存储了 bot 密码、recovery key、Synapse 地址。任何能读此文件的人都可接管 bot 账号。此脚本还创建第二个 Matrix 客户端操作同一 crypto.db，存在冲突风险。**建议删除或至少加密凭证部分。** 当前状态：保留作为参考，但不应直接运行。 |
| **🚨 方法定义缩进陷阱** | 在长方法中间插入 `async def` 会截断外层方法。把新方法定义放在末尾之后 |
| **🚨 sync 长连接被 GFW 半挂** | IPv6/4 到 Cloudflare 的长连接可能 ESTAB 但零流量。004 补丁含三重加固：IPv4 + force_close + 5s 短轮询 |
| **🚨 connect() 超时** | 30s 不够用 → `systemctl --user set-environment HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT=60` 后重启 Gateway |
| **🚨 aiohttp.ClientTimeout 无效** | 对已 ESTAB 的僵尸 socket 不生效。见 `references/ipv6-matrix-longpoll-hang.md` |
| **🚨 IPv6 long-poll 被 GFW 半挂** | Gateway sync 卡死，无新消息进来。重启或强制 IPv4（见 `references/ipv6-matrix-longpoll-hang.md`） |
| **🚨 DecryptionDispatcher 缺失** | Gateway 连接正常、能发消息但收不到任何入站消息。检查 `client.add_dispatcher` 是否有 `DecryptionDispatcher`。见 `references/decryption-dispatcher-missing.md` |
| **🚨 crypto_account.sync_token 为空** | crypto.db 清空后此字段为 `''`。通过 `sqlite3` 验证，影响待确认 |
| **🚨 Element 没有 Request keys 按钮** | 用户实测确认。在 Element UI 中无法主动请求 bot 的密钥。只能通过信任 bot 设备（设置 → 会话 → 验证）让 Element 自动分享密钥 |
| **🚨 `_on_encrypted_fallback` 静默崩溃** | `matrix.py:1003` 用 `client.mxid` 而非 `client.mxid`，每次收到需要 fallback 的加密事件就炸 → 2,500+ 次崩溃。密钥请求永远发不出去。修复：将第 1003 行 `client.mxid` 改为 `client.mxid`。诊断：`grep -c "has no attribute .user_id." ~/.hermes/logs/errors.log` |
| **🚨 密钥请求可能被用户 Element 拒绝** | 即使发送了 `m.room_key_request`，如果 bot 设备未被用户信任，mautrix 的 `allow_key_share` 会拒绝分享 → 入站会话始终为空 |

> 详情见 `references/device-id-reuse-unknown-device.md`

| **🚨 gateway restart 后立即退出（exit code 1）然后系统自恢复** | `systemctl --user restart` 会先发送 SIGTERM 给旧进程。如果旧进程关闭缓慢而新进程已启动，新进程的 `--replace` 会尝试 SIGTERM 已经在关闭的旧进程 → 可能同时关闭两个。旧 gateway 日志可见 `Exiting with code 1 (signal-initiated shutdown without restart request) so systemd Restart=on-failure can revive the gateway`。等待 5-10 秒 systemd 自动复活后检查。 |
| **🚨 设备 ID 复用导致跨签名后仍显示 '未知设备'** | crypto.db 清空后用**相同设备 ID**重建 → 新 identity key → 用户 Element 缓存旧 key → 即使 cross-signing 通过仍显示 "unknown device"。**同一设备 ID 绝对不能复用！** 每次清 crypto.db 必须生成全新 device ID（如 `hermes-bot-v$(date +%s)`）。执行 `full-e2ee-recovery-after-server-rebuild` 的 **Variant A**（保留 cross-signing + recovery key）即可快速修复，**无需用户任何操作**。详见 `references/device-id-reuse-unknown-device.md` |
| **🚨 非对称加密问题** | Gateway 有 outbound Megolm 会话（能发消息），但没有 inbound 会话（收不到用户回复）。两者独立修复：修复 DecryptionDispatcher + 用户信任 bot 设备 |

---

## 验证

1. `systemctl is-active` → active
2. 日志无 error/OTK
3. Element 显示 bot 在线
4. 测试消息双向通信正常
5. Gateway 日志中有 `Matrix: connected` + `✓ matrix connected`
6. sync 错误频率正常（E2EE 重建后：`grep -c "sync error" ~/.hermes/logs/gateway.log | tail -5` 应 < 20/天）

## 自动维护机制

| 机制 | 频率 | 说明 |
|:----|:----:|:-----|
| e2ee-watchdog.sh（cron） | 每 1 分钟 | Hermes cronjob 格式（no_agent=true），每分钟检测 E2EE 故障模式并触发 `e2ee-repair.py` 全量修复。当 `.e2ee-repairing` 锁文件存在时跳过修复。注意 `KillMode=mixed` 竞争条件。 |
| e2ee-health.sh | 已退役 | 与 watchdog 同批退役。 |
| e2ee-repair.py | 按需 | 全自动 E2EE 修复（被 watchdog 调用）|
| e2ee-repair-keys.py | 按需 | 重新共享 Megolm 密钥（v3 保留旧会话）|
| **e2ee-request-keys.py** | **按需** | **通过 REST API 手动发送密钥请求（不冲突）** |
| 004 补丁 auto-heal | 每次重连 | Gateway 自动修复（首选方案）|

补丁库：`~/.hermes/patches/`（含 README.md 升级恢复指南）
