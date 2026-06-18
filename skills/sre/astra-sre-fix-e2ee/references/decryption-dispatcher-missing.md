# DecryptionDispatcher 缺失 — 加密事件被静默丢弃

> 2026-06-07 首次发现并记录

---

## 现象

- Gateway 日志显示 `✓ matrix connected`，TCP 连接 ESTAB
- Gateway 可以发送加密消息（Outbound Megolm 会话正常）
- 但收不到任何入站消息（Element 上发的消息不进日志）
- crypto.db 的 `crypto_megolm_inbound_session` 表中，**所有行的 `sender_key` 都是 bot 自己的密钥**（`obTdrkw8rWz...`），没有来自 @nanaly 设备的入站会话

## 根因

### Event 处理链路

```
@nanaly 发消息 (m.room.encrypted)
  → Gateway sync_loop 收到 sync_data
  → client.handle_sync(sync_data) 分发事件
  → dispatch_event() 按 EventType 查找 handler
  → ❌ 没有 handler 注册给 EventType.ROOM_ENCRYPTED
  → 事件被 dispatch_event() 返回的空列表忽略 — 静默丢弃!
```

### 代码证据

在 `gateway/platforms/matrix.py` 的 `connect()` 方法中（~line 978-987）：

```python
# Register event handlers.
from mautrix.client import InternalEventType as IntEvt
from mautrix.client.dispatcher import MembershipEventDispatcher

client.add_dispatcher(MembershipEventDispatcher)        # ← 有
client.add_event_handler(EventType.ROOM_MESSAGE, ...)   # ← 有
# 没有 DecryptionDispatcher!
```

**注意：只注册了 `MembershipEventDispatcher`，没有 `DecryptionDispatcher`。**

### mautrix 的 DecryptionDispatcher

在 `mautrix/client/encryption_manager.py:167-188`：

```python
class DecryptionDispatcher(dispatcher.SimpleDispatcher):
    event_type = EventType.ROOM_ENCRYPTED
    client: client.Client

    async def handle(self, evt: EncryptedEvent) -> None:
        try:
            decrypted = await self.client.crypto.decrypt_megolm_event(evt)
        except DecryptionError as e:
            self.client.crypto_log.warning(f"Failed to decrypt {evt.event_id}: {e}")
            return                                 # ← 仅log，不请求密钥！
        self.client.dispatch_event(decrypted, evt.source)
```

即使注册了 `DecryptionDispatcher`，解密失败也只是 log 一个 warning 然后 return——**不会自动发送 `m.room_key_request`**。

### 为什么以前能工作

如果 crypto.db 正常（包含 @nanaly 的入站 Megolm 会话），mautrix 可以正常解密 `m.room.encrypted` 事件并派发为 `m.room.message`，再由 `_on_room_message` 处理。

但 crypto.db **被清空重建后**：
1. 旧的入站 Megolm 会话丢失
2. 没有 `DecryptionDispatcher` → 无人处理 `m.room.encrypted` 事件
3. 即使有 `DecryptionDispatcher` → 解密失败只 log → 不会自动请求密钥

## 诊断方法

### 1. 检查入站会话的来源

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('/home/alrcatraz/.hermes/platforms/matrix/store/crypto.db')
cur = db.execute('SELECT sender_key, room_id, session_id, received_at FROM crypto_megolm_inbound_session ORDER BY received_at DESC')
for row in cur.fetchall():
    is_bot = 'obTdrkw8rWz' in str(row[0])  # bot 的 identity key
    print(f'  [{\"BOT\" if is_bot else \"!! USER !!\"}] key={str(row[0])[:30]} room={str(row[1])[:30]} recv={row[3]}')
db.close()
"
```

全部是 `[BOT]` = 没有用户入站会话。

### 2. 检查 DecryptionDispatcher 注册状态

```bash
grep -n "DecryptionDispatcher\|add_dispatcher" ~/.hermes/hermes-agent/gateway/platforms/matrix.py
```

只有 `MembershipEventDispatcher` → 根因确认。

### 3. 检查 crypto_account.sync_token

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

`False`（空字符串）= to-device 同步可能受影响。

## 修复方法

### 方法 A：手动发送密钥请求（无需重启 Gateway）

使用 `e2ee-request-keys.py` 脚本：

```bash
cd ~/.hermes && source hermes-agent/venv/bin/activate
python3 scripts/e2ee-request-keys.py
```

脚本逻辑：
1. 查询 DM 房间最近的加密消息
2. 提取 `sender_key` 和 `session_id`
3. 通过 Matrix `sendToDevice` API 发送 `m.room_key_request`
4. 同时发送给用户的所有设备

**注意：** 使用 REST API 直接通信，不依赖运行中的 Gateway 客户端。

**⚠️ 重要陷阱：密钥请求可能被用户 Element 静默拒绝！**

即使成功发送了 `m.room_key_request`，用户 Element 的 `handle_room_key_request` → `allow_key_share` 可能会拒绝：

```python
# mautrix/crypto/key_share.py:48-87
async def default_allow_key_share(self, device, request):
    if device.user_id != self.client.mxid:
        raise RejectKeyShare(...)  # 不同用户
    elif device.trust == TrustState.BLACKLISTED:
        raise RejectKeyShare(code=BLACKLISTED, ...)  # 黑名单
    elif await self.resolve_trust(device) >= self.share_keys_min_trust:
        return True  # ✅ 信任
    else:
        raise RejectKeyShare(code=UNVERIFIED, ...)  # ❌ 未信任
```

核心检查：`resolve_trust(device) >= share_keys_min_trust`。
默认 `share_keys_min_trust = TrustState.VERIFIED`（需要设备被验证）。

**用户侧唯一解决方案：** 手动验证 bot 设备
1. Element → 设置 → 会话（Sessions）
2. 找到 `hermes-bot-v1780662000` → 验证/信任
3. 重新运行 `e2ee-request-keys.py`

**Element UI 确认：** ❌ Element **没有** "Request keys" 按钮
（用户 2026-06-07 实测确认。无法从 UI 触发密钥请求。）

### 方法 B：补丁 Gateway 代码

向 `gateway/platforms/matrix.py` 添加：

```python
from mautrix.client.encryption_manager import DecryptionDispatcher
client.add_dispatcher(DecryptionDispatcher)
```

**但仅注册不够**——还需处理 `DecryptionError` 时调用 `request_room_key()`。

## 关联问题

### crypto_account.sync_token 为空

crypto.db 清空后，`crypto_account.sync_token` 为 `''`。可能导致 mautrix OlmMachine 的 to-device 消息同步异常。正常运行时此 token 为 base64 字符串。

### 跨签名验证 ≠ 用户设备信任（2026-06-07 新发现）

这是一个关键区分：

| 层面 | 操作 | 状态 |
|:----|:-----|:-----|
| ✅ Bot 侧 | `olm.verify_with_recovery_key(recovery_key)` | Bot 自签完成，设备在服务端标记为 cross-signed |
| ❌ 用户侧 | Element 的 `allow_key_share` 检查 | Bot 设备信任等级 < VERIFIED → 密钥请求被拒绝 |

即使 bot 用 recovery key 完成了跨签名验证，用户的 Element **不会自动同步**这个信任关系。用户必须手动进设置验证设备。

### 非对称加密现象（2026-06-07 新发现）

**表现：** Gateway 可以发送加密消息（用户能收到），但用户回复的消息 Gateway 解密不了。

**原因：** 这两个通道使用独立的 Megolm 会话：
- **出站（Bot→用户）：** Bot 的 outbound Megolm session，已在 `share_group_session` 时分享了密钥给用户 → 用户能解密 ✓
- **入站（用户→Bot）：** 用户的 outbound Megolm session，密钥在用户设备上 → Bot 需要被用户信任才能收到密钥分享 ✗

**修复需要两步（缺一不可）：**
1. Gateway 侧：注册 `DecryptionDispatcher` + 密钥请求逻辑（代码补丁）
2. 用户侧：在 Element 中验证 bot 设备（设置 → 会话 → 验证）
