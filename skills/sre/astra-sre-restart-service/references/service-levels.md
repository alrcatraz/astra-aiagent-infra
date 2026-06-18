# 服务等级参考

按重启影响面分 L2/L3：

| 服务 | 类型 | 等级 | 重启影响 |
|:-----|:----|:----:|:---------|
| hermes-gateway | 用户服务 (systemd --user) | L3 🔴 | 中断所有平台消息收发，断当前对话 |
| postgresql | 系统服务 | L3 🔴 | 所有依赖 PG 的 MCP、知识库一起断 |
| searxng-core | 容器 (podman) | L2 🟡 | web_search 降级，SearXNG 不可用 |
| easytier-core | 系统服务 | L3 🔴 | 组网中断，HK/UK/NAS 远程访问断开 |
| tailscaled | 系统服务 | L3 🔴 | Tailscale 网络中断 |
| sshd | 系统服务 | L2 🟡 | 新 SSH 连接断开，已有会话不受影响 |
| mcp-server-* | 用户进程 | L2 🟡 | 单个 MCP 不可用，其他正常 |
| NetworkManager | 系统服务 | L3 🔴 | 网络中断 |

## 判断原则

- `systemctl list-dependencies <service>` 查看依赖者
- 不确定时默认 L3（找你确认）
