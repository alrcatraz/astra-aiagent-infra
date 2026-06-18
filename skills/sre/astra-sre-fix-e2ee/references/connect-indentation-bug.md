# 方法定义缩进陷阱：中间插一个 `async def` 会截断外层方法

> 2026-06-07 发现：在 `connect()` 方法体中插入了 `async def _deferred_reshare_rooms` 方法定义（4 空格缩进），导致后续的 `try:` 块（8 空格）不属于 `connect()` 而是属于新方法。

## 问题症状

Gateway 日志显示一切正常（whoami、cross-signing、initial sync 都成功了），但日志中无 `connected` 标记，`systemctl status` 显示在反复重连：

```
17:16:25 initial sync complete, joined 3 rooms
17:16:26 disconnected     ← 1 秒就断，但没有任何错误日志
17:16:26 ✗ failed to connect
```

## 根因

Python 使用**缩进**而不是大括号来确定作用域。看这段错误的结构：

```python
class MatrixPlatform(BasePlatformAdapter):

    async def connect(self):              ← 4 空格（类方法）
        ...                                ← 8 空格（方法体）
        if self._encryption:
            ...                            ← 12 空格（if 块）
            asyncio.create_task(...)       ← 12 空格 ← connect() 在这里隐式结束
    
    async def _deferred_reshare_rooms(self):  ← 4 空格（新方法！）
        """..."""
        try:                              ← 8 空格 ← 属于新方法，不是 connect()！
            self._sync_task = asyncio.create_task(self._sync_loop())
            self._mark_connected()
            return True                   ← 在新方法里，用户收不到
        except Exception:
            return False                  ← 也在新方法里

    async def disconnect(self):            ← 4 空格
```

**`async def _deferred_reshare_rooms`（4 空格）在源文件中出现在 `connect()` 方法体（8 空格）中间。** Python 解析器看到缩进回到 4 空格 → 认定 `connect()` 结束了 → 后续 8 空格的代码属于新方法。

`connect()` 隐式返回 `None` → `_connect_adapter_with_timeout` 收到 `None`（假值）→ 输出 `✗ matrix failed to connect`。

## 复现条件

在长方法中（如 `connect()` 数百行），想加入一个新的辅助方法时，**如果在方法体中间写 `def` 定义，Python 会认为外层方法已结束。**

## 修复

**把辅助方法定义移动到包含方法之外**（类级别，在 `connect()` 结束后）：

```python
    async def connect(self):
        ...
        return True       # connect() 在这里明确结束

    async def _deferred_reshare_rooms(self):   # ← 类级别，不在 connect 内部
        ...
```

确保 `connect()` 末尾的 `return True` 真的在 8 空格缩进，且是 `connect()` 方法体的最后一行。

## 验证

```bash
# 检查方法体是否正确闭合
grep -n "return True" gateway/platforms/matrix.py

# 确认 connect 和 _deferred_reshare_rooms 是同级方法
grep -n "async def " gateway/platforms/matrix.py | head -10
```

输出应该类似：
```
710:    async def connect(self) -> bool:
1052:    async def _deferred_reshare_rooms(self) -> None:
1104:    async def disconnect(self) -> None:
```

每个 `async def` 都是 4 空格缩进，表示它们是同一类的平行方法。

## 预防

编辑长方法时：

1. **加中间辅助方法时，一定放在包含方法的末尾之后**，不要插在中间
2. 编辑后验证缩进：`sed -n 'LINE_NUMBERp' file.py | cat -An` 看实际缩进字符数
3. 不信任肉眼——用 `cat -A` 或 `awk '{print NR": "$0}'` 检查
