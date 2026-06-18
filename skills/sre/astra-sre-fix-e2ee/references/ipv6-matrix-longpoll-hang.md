# IPv6 / IPv4 Matrix 长连接被 GFW 半挂

> 2026-06-07 发现：Gateway 使用 IPv6 连接到 Cloudflare 上的 Matrix
> 服务器时，sync long-poll TCP 连接 ESTABLISHED 但零流量，永不超时。

## 症状

Gateway 日志的最后一条是 `kanban dispatcher` 或 `Press Ctrl+C to stop`，
之后**任何新消息都不再被接收**（无 `inbound message` 日志）。
Gateway 显示 `active`，Element 显示 bot 在线，但消息发不进来。

`ss -tpn | grep hermes` 显示一个 ESTAB 连接，send-q 和 recv-q 均为 0：

```
# IPv6 被挂：
ESTAB      0      0   [2409:8a28::...]:48028
  [2606:4700:3030::6815:4e5a]:443   users:(("hermes",pid=2211027,fd=20))

# IPv4 同样被挂（GFW 也会半开 Cloudflare 的 IPv4 长连接）：
ESTAB      0      0   192.168.0.200:57426
  104.21.78.90:443   users:(("hermes",pid=2212606,fd=20))
```

- 连接持续 15+ 分钟无任何流量
- 无 `sync error` 日志（正常情况应每 ~10 秒重试）

## 根因

Matrix sync 使用 HTTP 长连接轮询（long-poll）。连接到 Cloudflare 时：
- **IPv6** (2606:4700:3030::...) — GFW 半开 TCP，零流量不超时
- **IPv4** (104.21.78.90 / 172.67.219.19) — GFW 也会半开，但概率略低

`asyncio.wait_for(sync_call, timeout=45.0)` 理论上应触发超时，
但 aiohttp 的底层 socket read 在某些情况下不响应 asyncio 的取消信号
（socket 处于 ESTAB 但无数据状态，read 系统调用不返回）。

**为什么之前 22 小时没问题？**
之前 Cloudflare DNS 返回了 IPv4(104.21.78.90)，且 sync timeout=30s 配合
wait_for 45s 恰好逃过了 GFW 的检测窗口。
之后 DNS 切换或重启导致 IPv6 优先，触发了此问题。

## 诊断

```bash
# 1. 检查 Gateway 有无活跃 sync 连接
ss -tpn | grep hermes

# 2. 检查连接目标 IP
ss -tpn | grep hermes | grep -oP '(\d+.\d+.\d+.\d+)|\[?[0-9a-f:]+:[0-9a-f:]+\]?' | tail -1

# 3. 判断：
#    IPv6 (2606:、2400: 等) -> 强制 IPv4
#    IPv4 (104.xx、172.xx) -> 需要短轮询
#    无连接 -> 检查 Gateway 是否在重连中

# 4. 检查 connect() 是否超时
grep "timed out\|failed to connect" ~/.hermes/logs/gateway.log | tail -3
```

## 修复方案

### 方案 A：完整方案（004 补丁已包含）

004 patch 已包含三重加固，一次应用即可：

```bash
cd ~/.hermes/hermes-agent
git apply patches/004-gateway-e2ee-autoheal.patch
```

补丁包含：

| 加固 | 作用 | 效果 |
|:----|:-----|:----:|
| `family=socket.AF_INET` | 强制 Matrix HTTP 连接用 IPv4 | 规避 IPv6 被半挂 |
| `force_close=True` | 每次请求后主动关闭 TCP | 避免长连接积累半开状态 |
| sync timeout 30s->5s | 短轮询替代长轮询 | 即使被挂，15 秒后重试 |

### 方案 B：仅强制 IPv4（不重启 Gateway）

修改 `gateway/platforms/matrix.py` 中 `_create_matrix_session` 函数，
给 `TCPConnector` 加 `family=socket.AF_INET` 后重启 Gateway。

### 方案 C：增加 connect() 超时

如果 connect() 超时（日志显示 "timed out after 30s"）：

```bash
systemctl --user set-environment HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT=60
hermes gateway restart
```

**`systemctl set-environment` 设的是 systemd 用户会话环境变量，新 Gateway 进程会继承。**
重启 Gateway 生效。

## 已验证无效的尝试

| 尝试 | 原因 |
|:----|:-----|
| `aiohttp.ClientTimeout(total=20)` | aiohttp 3.13 的 `ClientTimeout` 对半开 socket 不起作用——socket 处于 ESTAB 状态（非连接超时），读操作不响应 timeout |
| `tcp_keepalive=True` 等参数 | aiohttp 3.13 的 `TCPConnector` 不支持这些参数 |

## 长期方向

Matrix sync 在 GFW 环境下长连接本质上不可靠。需要两层面加固：

1. **sync 层：短轮询而非长轮询** — 5s 超时，最多等 15s 重试
2. **HTTP 层：强制 IPv4 + 关闭长连接** — `force_close=True`

004 补丁已经处理了这两个层面。
