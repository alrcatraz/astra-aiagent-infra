# 零出站会话 — crypto.db 清空后的 E2EE 恢复实战记录

> 2026-06-07 实战记录。场景：用户报告"无法解密的消息"，排查发现 Gateway 两个房间均为`无出站会话`。

---

## 场景特征

| 维度 | 表现 |
|:----|:------|
| Gateway 状态 | ✅ active，cross-signing verified |
| 日志 | ❌ 无 OTK 错误、无 decrypt error |
| `check-crypto-state.py` | `无出站会话`（两个房间都是） |
| `e2ee-repair-keys.py` | `!xxx → 无出站会话` → **主动创建新会话 → shared=1** |
| 用户现象 | 旧消息🔒无法解密，Gateway 本身能收消息 |

## 根因

crypto.db 被删除（设备 ID 重置或全新部署）后，Gateway 重启时**不会自动创建 outbound Megolm 会话**。出站会话只在 Gateway **第一次发消息**时创建。如果用户先发了消息（创建了 inbound 会话但无 outbound），双方加密通道不对等。

**关键洞察：** `deferred re-share` 机制（004 补丁）只重新分享**已有**会话的密钥——当 outbound sessions 数量为 0 时，它什么也不做。被动等待不会解决问题。

## 修复

```bash
cd ~/.hermes
source hermes-agent/venv/bin/activate
python3 scripts/e2ee-repair-keys.py
```

脚本在没有出站会话时会：
1. 创建全新的 Megolm 出站会话
2. 自动分享密钥到用户设备（`shared=1`）
3. 输出 `successfully shared`

## 注意事项

- 首次运行会打印 `No one-time keys nor device keys got` 警告——**这是正常的**，因为客户端还没上传 OTK。后续运行不会再出现
- 脚本在 Gateway 运行状态下执行：零出站会话场景下冲突风险低（没有旧会话可被误删）
- 旧消息无法恢复——因为旧 Megolm 会话密钥已被删除。用户需要点 🔒 → Request keys 尝试恢复
- 修复后 Gateway 可以正常收发加密消息

## 关联

- `full-e2ee-recovery-after-server-rebuild` — 完整的服务器重建后 E2EE 恢复流程
- `astra-sre-fix-e2ee` — 主 E2EE 修复 skill（此文件已被引用）
