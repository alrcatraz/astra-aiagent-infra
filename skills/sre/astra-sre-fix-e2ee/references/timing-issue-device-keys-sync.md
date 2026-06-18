# Auto-heal 时序问题：设备列表尚未同步

> 2026-06-07 发现：004 补丁的 immediate auto-heal 在 Gateway 启动后立即触发，此时设备列表可能尚未从服务器同步完成，导致 share_group_session 找不到用户设备，但仍设置 shared=True。
>
> 2026-06-07 修复：改为 deferred approach（30 秒后重试），同时修复了方法定义缩进 bug 导致 connect() 返回 None 的问题。

## 问题现象

Gateway 重启后日志显示：
```
Matrix: created fresh Megolm session for !fjNpoF...  ✅ 自动创建
Matrix: created fresh Megolm session for !HNjfC...   ✅ 自动创建
```

但用户侧消息仍显示"无法解密"。

## 根因分析

`share_group_session()` 的流程：

```python
async def _share_group_session(self, room_id, users):
    session = self._new_outbound_group_session(room_id)
    
    for user_id in users:
        devices = await self.crypto_store.get_devices(user_id)
        if devices is None:  # ← 设备未同步
            fetch_keys.append(user_id)
    
    fetched_keys = await self._fetch_keys(users, include_untracked=True)
    
    # 如果 still no devices → olm_sessions 为空 → 跳过加密
    # 但 shared=True 仍然执行！
    session.shared = True
    await self.crypto_store.add_outbound_group_session(session)
```

**关键 bug：** 当设备列表为空或 `_fetch_keys` 未返回任何设备时，`_encrypt_and_share_group_session` 不会被调用，但 `session.shared = True` 仍然执行。

## 修复：Deferred Re-share（004 补丁）

加入 `_deferred_reshare_rooms()` 方法，30 秒后重试 + 5×5s 重试逻辑：

```python
async def _deferred_reshare_rooms(self) -> None:
    await asyncio.sleep(30)
    for attempt in range(5):
        client = getattr(self, "_client", None)
        if client and client.crypto and hasattr(..., "reset_outbound_session_sharing"):
            break
        await asyncio.sleep(5)
    else:
        return  # 放弃
    
    for room_id in self._joined_rooms:
        session.shared = False
        await crypto_store.add_outbound_group_session(session)
        await crypto.share_group_session(room_id, users)
```

**日志验证：** `Matrix: deferred re-share complete for 3 room(s)` ✅

## 附注：方法定义缩进 bug

第一版修复中，`async def _deferred_reshare_rooms` 定义被放在了 `connect()` 方法体中间（4 空格缩进），导致 `connect()` 在中间隐式结束，返回 `None`。修复方法见 `references/connect-indentation-bug.md`

## 手动修复（仅当 004 失败时）

```bash
cd ~/.hermes
source hermes-agent/venv/bin/activate
python3 scripts/e2ee-repair-keys.py
```

> ⚠️ 注意冲突风险：脚本创建第二个 Matrix 客户端，可能干扰 Gateway。
