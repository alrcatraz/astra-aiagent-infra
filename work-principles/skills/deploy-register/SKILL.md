---
name: deploy-register
description: "Mandatory registration checklist after deploying a new service or facility: register in service inventory, attach health checks, clean up residuals."
category: devops
triggers:
  - "部署完登记"
  - "service inventory 注册"
  - "新服务上线收尾"
  - "deploy checklist"
  - "健康检查挂上"
metadata:
  hermes:
    tags: [deployment, registration, inventory, health-checks]

---
# deploy-register

## Trigger Conditions

This skill is automatically loaded when the task involves:
- Deploying, installing, starting, or registering a service
- Configuring a service, exposing a port, going live, publishing
- Any new service, MCP server, CLI tool, or other facility deployed for the agent

Also triggered by: 部署、安装服务、启动服务、注册服务、配置服务、暴露端口、上线、发布

> **Routing:** Prefer loading `execution-framework` first; it will route here when the task involves deployment.

## Checklist

- [ ] **服务信息已登记到服务清单？**
  - 名称、部署位置、端口、用途、健康检查方式
- [ ] **是否已接入自动化健康检查？**
  - 是 → 编写或更新检查脚本
  - 否 → 登记待办事项
- [ ] **astra-aiagent-infra 生态登记？**（如项目属于 astra 生态）
  - 在 `registry.yaml` 添加组件条目（type: skill/sre/mcp/infra）
  - 在 `README.md` 的 Component Overview 表格添加一行
- [ ] **是否已更新知识库？**（服务/MCP → `hermes_config` KB；修复/trick → `sre_incidents` KB）
  - 通过 `kb_add(kb='hermes_config', ...)` 记录服务名称、端口、路径、健康检查方式、已知问题
  - 参见 `service-inventory` New Service Checklist 第4步了解两种 kb_hermes_config 的区别
- [ ] **依赖关系是否已标注？**（如属于 astra 生态且在 public GitHub 上）
  - 在 meta-repo `registry.yaml` 的组件条目中添加 `depends_on` 字段
  - 在本仓库 `README.md` 添加 Dependencies 表格
  - 如有必要，更新 `AGENTS.md` 的 Dependencies 部分
- [ ] **是否有旧版本、旧进程或旧配置需要清理？**
- [ ] **部署过程中是否产生了临时文件？** 清理了吗？
- [ ] **如果将来移除这个服务，需要清理什么？** 数据库记录、检查脚本、引用文档。
- [ ] **部署形态已登记，且按形态做了对应的完整性检查？**
  - 先判定该资产的形态（inventory 的 `references/deployment-forms.md`），再按该形态的
    checklist 走——不是所有资产都走 symlink 桥
  - 链接桥接型：**双向 + 可用性** 三查（每个组件有链接 / 每个链接解析到生产副本 /
    链接名=注册名可被加载），`missing=0 且 broken=0 且 stale=0` 才算完成
  - 链接全对 ≠ 技能可用：只验证"存在的链接是活的"会漏掉整批未注册的组件，
    必须用生产副本的组件全集做分母（正向枚举），不能以链接集为分母



<!-- LIFECYCLE_HOOKS_BEGIN -->
**Deploy lifecycle hooks — auto-generated.** Do not edit manually.
Run `astra-lifecycle-sync --update` to refresh.

### From work-principles
- [🔴] 部署新服务后注册到服务清单 + 健康检查 → 详见 work-principles/skills/deploy-register
  *(required, trigger: new service, MCP, or CLI tool deployed)*

### From astra-hub
- [🔴] 验证 Hub 项目索引表包含所有 registry 中已注册的组件（不含已吸收的独立条目）
  *(required, trigger: registry.yaml modified（新增/移除组件）)*
  ```bash
  grep -c '|' ~/Projects/astra/astra-aiagent-infra/skills/devops/astra-hub/SKILL.md | head -1 || echo 'Manual check: compare Hub index vs registry.yaml components'
  ```

### From astra-vcs-assist
- [🔴] Register all sub-skill symlinks in Hermes discovery path
  *(required, trigger: new clone or first deploy of vcs-assist)*
  ```bash
  mkdir -p "$HOME/.hermes/skills/vcs" && ln -sfn "$HOME/.astra/repos/astra-vcs-assist" "$HOME/.hermes/skills/vcs/astra-vcs-assist" && for d in gpg/astra-vcs-assist-gpg-key git/skills/astra-vcs-assist-git-init git/skills/astra-vcs-assist-git-dev git/skills/astra-vcs-assist-git-release git/skills/astra-vcs-assist-git-sync; do ln -sfn "$HOME/.astra/repos/astra-vcs-assist/$d" "$HOME/.hermes/skills/vcs/$(basename $d)"; done

  ```
- [🔴] Verify all sub-skill SKILL.md files exist
  *(required, trigger: deploy or update of vcs-assist)*
  ```bash
  for f in SKILL.md gpg/astra-vcs-assist-gpg-key/SKILL.md git/skills/astra-vcs-assist-git-init/SKILL.md git/skills/astra-vcs-assist-git-dev/SKILL.md git/skills/astra-vcs-assist-git-release/SKILL.md git/skills/astra-vcs-assist-git-sync/SKILL.md; do test -f "$HOME/.astra/repos/astra-vcs-assist/$f" || echo "MISSING: $f"; done

  ```

### From astra-sre
- [🔴] Register new device in SRE config/devices.yaml
  *(required, trigger: new device added to infrastructure)*

<!-- LIFECYCLE_HOOKS_END -->


## Pitfalls

1. **部署完就走 = 管理黑洞。** 未记录的服务发生故障时，你不会意识到它的存在。
2. **服务清单不是一次性的。** 移除服务时，必须在此注销并彻底清理所有引用。
3. **此清单不会自动感知新的子系统类型。** 如果未来新增了不属于 skill/sre/mcp/infra 的组件类型，需要手动更新本检查清单。目前的检查项涵盖的服务类型是静态的。
4. **生命周期钩子需要手动传播。** 在 `~/.astra/repos/astra-aiagent-infra/registry.yaml` 中添加的 `lifecycle.deploy` 钩子需要运行 `python3 lifecycle/astra-lifecycle-sync.py --update` 才能注入到本 SKILL.md 的 Ecosystem Hooks 章节。如果钩子明明加了却没显示，检查是否忘了跑同步。
