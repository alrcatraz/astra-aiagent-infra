# astra-skill-change-safeguard
<div align="center">

[![License](https://badgen.net/github/license/alrcatraz/astra-skill-change-safeguard)](LICENSE) [![GitHub stars](https://badgen.net/github/stars/alrcatraz/astra-skill-change-safeguard)](https://github.com/alrcatraz/astra-skill-change-safeguard) [![GitHub last commit](https://badgen.net/github/last-commit/alrcatraz/astra-skill-change-safeguard)](https://github.com/alrcatraz/astra-skill-change-safeguard/commits)

</div>

Pre-change safeguarding checks and post-change side-effect scan for Hermes Agent. Provides three-tier backup strategy, environment baseline recording, and a five-point post-change scan.

## Features

- Pre-change preservation: three-tier backup (server / project / file) + environment baseline recording
- Post-change audit: root cause analysis, same-pattern scan, side-effect review, newly exposed issues, residual cleanup
- Pitfall reminders: verify after each step, baseline even for small changes, "target met" is only half the job

## Install

Copy `SKILL.md` to your Hermes profile's `skills/` directory:

```bash
cp SKILL.md ~/.hermes/profiles/default/skills/change-safeguard.md
```

## Dependencies

This skill has no external dependencies. Its checklist is self-contained.

## Related

- [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra) — ecosystem portal

## License

MIT — see [LICENSE](LICENSE).

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=alrcatraz/astra-skill-change-safeguard&type=date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=alrcatraz/astra-skill-change-safeguard&type=date" />
    <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=alrcatraz/astra-skill-change-safeguard&type=date" width="600" />
  </picture>
</div>

---

## 中文版

### 功能

- 事前保全：三层备份（服务器/项目/文件）+ 环境基线记录
- 事后审计：根因定位、同类扫描、副作用审查、新暴露问题、残留清理
- 防坑提醒：分步验证、小改动也走基线、"达标就收工"是半套

### 安装

将 `SKILL.md` 复制到 Hermes profile 的 `skills/` 目录下：

```bash
cp SKILL.md ~/.hermes/profiles/default/skills/change-safeguard.md
```

### 依赖关系

此 skill 无外部依赖，检查清单完全自包含。
