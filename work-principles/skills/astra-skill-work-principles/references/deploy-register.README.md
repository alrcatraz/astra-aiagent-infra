# astra-skill-deploy-register

部署新服务或设施后强制执行的登记清单 Hermes Agent skill。确保每个新部署的服务都注册到服务清单、接入健康检查、清理残留。

## 功能

- 自动化登记：服务部署后强制注册名称/端口/用途/健康检查方式
- 健康检查接入：确保部署后立即接入自动化检查
- 清理检查：旧版本/旧进程/临时文件清理 + 未来移除计划

## 安装

将 `SKILL.md` 复制到 Hermes profile 的 `skills/` 目录下：

```bash
cp SKILL.md ~/.hermes/profiles/default/skills/deploy-register.md
```

## License

MIT — 详见 [LICENSE](LICENSE)
