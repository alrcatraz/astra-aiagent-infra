# Device ID Reuse — "未知设备" 根因

## 问题现象

- ✅ Cross-signing 已验证（Gateway 日志: `cross-signing verified via recovery key`）
- ✅ Element DM 房间显示 hermes-bot 为 "已验证"
- ✅ Gateway 能发消息（outbound Megolm 正常）
- ❌ 用户回复显示 "由未知或已被删除的设备加密"
- ❌ 密钥请求（`m.room_key_request`）被用户 Element 静默拒绝
- ❌ crypto.db 所有入站 Megolm 会话都是 bot 自己的密钥（sender_key = bot's identity key）

## 根因

当 crypto.db 被清空后重建时：

1. **设备 ID 被复用**（如 `hermes-bot-v1780662000`）
2. 新 crypto.db 生成**全新的 identity key**（ed25519 密钥对）
3. Gateway 上传新设备密钥到 Synapse，并用 recovery key 重新签名
4. **用户 Element 缓存了旧的 identity key**（关联到同一设备 ID `hermes-bot-v1780662000`）
5. 收到消息时：设备 ID 匹配但 identity key 不匹配 → "由未知或已被删除的设备加密"

## 跨签名 ≠ 设备信任

- **跨签名验证**（`olm.verify_with_recovery_key()`）：bot 用 recovery key 签署自己的设备 → 服务器上 bot 设备显示为 cross-signed
- **设备信任**（用户 Element 侧）：用户 Element 有旧 identity key 缓存 → 即使 cross-signed 通过，仍然显示 "未知设备"

**关键差异：** 跨签名说 "此设备被主人密钥签署"，但缓存冲突说 "此设备的密钥和以前不一样"。

两者是独立判断的。跨签名通过 ≠ 设备被信任。

## 解决方案

### 方案 A：全新设备 ID + 保留跨签名（推荐 ✅ — 无需用户操作）

用**从未使用过的**设备 ID 生成新 access token，同时**保留跨签名密钥和 recovery key**（不删 `e2e_cross_signing_keys` 和 `account_data`）：

```python
# 在 Synapse 服务器上: 需要 bot 密码
NEW_DEVICE = "hermes-bot-v" + str(int(time.time()))
```

流程：
1. 生成全新设备 ID（`hermes-bot-v<TIMESTAMP>`）
2. 用 password login 获取新 token（**不要**删 cross-signing keys 和 account_data）
3. 更新 `~/.hermes/.env` 的 `MATRIX_ACCESS_TOKEN` 和 `MATRIX_DEVICE_ID`
4. 删除旧的 crypto.db
5. 重启 Gateway
6. ✅ **Gateway 自动用 recovery key 恢复跨签名 → `cross-signing verified via recovery key`**
7. ✅ **无需用户操作** — recovery key 为新设备签名，所有客户端因 master key 一致而自动信任

> **为什么不用验证？** Recovery key 恢复了 bot 的 master cross-signing key。用户 Element 已经信任了这个 master key（之前的验证），所以由它签署的新设备自动受信。

### 方案 B：全新设备 ID + 核弹级重置（用户需操作）

当跨签名本身也被损坏或 recovery key 不可用时：

1. 删所有 E2EE 相关数据（含跨签名、account_data）
2. 生成全新 device ID
3. 用 password login 获取新 token
4. 更新 .env + 清 crypto.db
5. 启动 Gateway（无 recovery key → cross-signing 未建立）
6. 用户登录 Element Web bot 账号 → 设置安全短语 + 恢复密钥
7. 用户验证新设备
8. 恢复密钥写 .env
9. 重启 Gateway

### 方案 C：用户在 Element 中手动信任（不换设备 ID）

> ⚠️ 此方案**不是根治**。同一设备 ID + 不同 identity key → Element 缓存冲突持续存在。推荐用方案 A。

### 方案 D：用户要求旧消息重新加密

1. 在 Element 中打开 DM 房间
2. 对任意 bot 的消息：点击 🔒 → **查看详细信息**
3. 选择 **信任此会话**
4. Element 自动请求密钥并解密历史消息

> ⚠️ 此选项在不同 Element 版本中是否存在未知。如果不存在，用方案 A 或 B。

## 验证

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('/home/alrcatraz/.hermes/platforms/matrix/store/crypto.db')
cur = db.execute('SELECT sender_key FROM crypto_megolm_inbound_session')
for row in cur.fetchall():
    is_bot = 'obTdrkw8rWz' in str(row[0])
    print(f'  KEY: {str(row[0])[:30]}... (\"BOT\" if is_bot else \"USER\")')
db.close()
"
```
