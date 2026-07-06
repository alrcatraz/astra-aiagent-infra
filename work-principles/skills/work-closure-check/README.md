# astra-skill-work-closure-check
<div align="center">

[![License](https://badgen.net/github/license/alrcatraz/astra-skill-work-closure-check)](LICENSE) [![GitHub stars](https://badgen.net/github/stars/alrcatraz/astra-skill-work-closure-check)](https://github.com/alrcatraz/astra-skill-work-closure-check) [![GitHub last commit](https://badgen.net/github/last-commit/alrcatraz/astra-skill-work-closure-check)](https://github.com/alrcatraz/astra-skill-work-closure-check/commits)

</div>

Mandatory closure checklist when wrapping up a task for Hermes Agent. Provides a six-stage systematic check: credential leak scan, skill update evaluation, decision record documentation, service/device registration, information storage verification, and environment baseline comparison.

## Features

- Six-stage closure check: credential leak → skill update → decision record → service/device registration → information storage → environment baseline
- Standardised closure procedure: notify → wait for confirmation → clean → summarise → final offer
- Pitfall reminders: don't skip confirmation, don't confuse skill/memory boundaries, cross-session credential residuals

## Install

Copy `SKILL.md` to your Hermes profile's `skills/` directory:

```bash
cp SKILL.md ~/.hermes/profiles/default/skills/work-closure-check.md
```

## Dependencies

| Repository | Resource | Required | Purpose |
|:-----------|:---------|:--------:|:--------|
| [astra-sre](https://github.com/alrcatraz/astra-sre) | Two-Strike Rule (skill creation decision tree) | Optional | Skill creation vs patching decisions during closure |
| [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra) | `docs/credential-schema.md` | Optional | Credential leak scan references credential storage conventions |

## Related

- [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra) — ecosystem portal

## License

MIT — see [LICENSE](LICENSE).

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=alrcatraz/astra-skill-work-closure-check&type=date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=alrcatraz/astra-skill-work-closure-check&type=date" />
    <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=alrcatraz/astra-skill-work-closure-check&type=date" width="600" />
  </picture>
</div>

---

## 中文版

### 功能

- 六阶段闭环检查：凭证泄露 → 技能更新 → 决策记录 → 服务/设备登记 → 信息存储 → 环境基线对比
- 标准化收尾流程：通知 → 等待确认 → 清理 → 汇总 → 再问
- 防坑提醒：不跳过确认、不混淆 skill/记忆、凭证跨 session 残留检查

### 安装

将 `SKILL.md` 复制到 Hermes profile 的 `skills/` 目录下：

```bash
cp SKILL.md ~/.hermes/profiles/default/skills/work-closure-check.md
```

### 依赖关系

| 仓库 | 资源 | 必须 | 用途 |
|:-----|:-----|:----:|:-----|
| [astra-sre](https://github.com/alrcatraz/astra-sre) | Two-Strike Rule（skill 创建决策树） | 可选 | 收尾时关于创建还是修补 skill 的决策 |
| [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra) | `docs/credential-schema.md` | 可选 | 凭证泄露扫描引用的凭证存储规范 |
