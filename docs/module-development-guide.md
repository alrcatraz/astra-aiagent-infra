# Module Development Guide

> Mandatory and recommended requirements for every component in the Astra
> ecosystem. New modules MUST satisfy all mandatory requirements before they
> are considered complete.
>
> If you are reading this before creating your first module, start by cloning
> the [project template](#1-repository-standards) — it provides the canonical
> project skeleton and saves you from building it by hand.

---

## 1. Repository Standards

The canonical project skeleton lives in the
[astra-aiagent-infra-template](https://github.com/alrcatraz/astra-aiagent-infra-template)
repository. Every new module SHOULD be created by using GitHub's
**"Use this template"** button, or by mirroring the template's structure
manually.

### 1.1 README

Every module MUST include a `README.md` with the following structure, in order:

1. **Title and subtitle** — a one-line description of the module.
2. **Badge bar** — wrapped in `<div align="center">`, containing four badges:
   - License: `https://badgen.net/github/license/alrcatraz/<repo>`
   - GitHub stars: `https://badgen.net/github/stars/alrcatraz/<repo>`
   - Last commit: `https://badgen.net/github/last-commit/alrcatraz/<repo>`
   - Sponsor: `https://img.shields.io/github/sponsors/alrcatraz?label=Sponsor&logo=github&color=ea4aaa&logoColor=white`
3. **English documentation body** — sections covering overview, setup,
   configuration, usage, architecture, related projects, and licence.
4. **`---` horizontal rule.**
5. **Full Chinese translation** — the same content rendered in Chinese, with a
   Chinese heading (e.g. `# <name>（中文版）`).

The badge bar MUST appear immediately after the subtitle, before any section
heading. The template's `README.md` contains the exact HTML and Markdown
markup to copy.

### 1.2 SKILL.md (Hermes Skills Only)

Every Hermes skill MUST declare a YAML frontmatter block at the top of its
`SKILL.md`. The frontmatter MUST contain the following keys:

```yaml
---
name: astra-<domain>-<subdomain>
description: "<one-line summary of what this skill covers>"
version: <MAJOR.MINOR.PATCH>
author: alrcatraz
platforms: [linux]
---
```

- The `name` field MUST use kebab-case and MUST be prefixed with `astra-`.
- The `version` field MUST follow Semantic Versioning 2.0.0
  (see [§5 Version Management](#5-version-management)).
- Modules with sub-skills (orchestrator skills) SHOULD list linked skills in a
  `related_skills` field.

### 1.3 AGENTS.md

Modules that expose CLI commands, API endpoints, or MCP tools SHOULD include an
`AGENTS.md` that documents entry points, environment variables, dependencies,
and typical agent workflows. The template provides a skeleton with `{{ }}`
placeholders.

### 1.4 LICENSE

Every module MUST include a `LICENSE` file. The standard licence for Astra
ecosystem components is **MIT**. Modules that contain documentation exclusively
MAY use **CC-BY-SA 4.0** instead.

---

## 2. Registry Registration

Every module MUST be registered in the ecosystem registry at
[astra-aiagent-infra/registry.yaml](../registry.yaml).

### 2.1 Entry Requirements

The registry MUST contain a YAML entry with the following keys:

```yaml
- type: <skill|sre|mcp|infra|tutorial>
  name: <module-name>
  repo: alrcatraz/astra-<module-name>
  version: <X.Y.Z>
  description: <one-paragraph summary>
  status: <active|stable|planned|deprecated>
  depends_on: []
```

- `name` MUST match the module's directory name in `~/Projects/astra/`.
- `repo` MUST be the GitHub repository path (`alrcatraz/astra-<name>`).
- `status` follows the lifecycle defined in
  [component-lifecycle.md](component-lifecycle.md).

### 2.2 Version Consistency

The `version` field in `registry.yaml` MUST match every other declaration of
the same version in the module's source tree. Specifically:

| File | Field to verify |
|:-----|:----------------|
| `registry.yaml` | `version` |
| `SKILL.md` frontmatter | `version` |
| `pyproject.toml` | `project.version` |

Before publishing any release, verify consistency by running:

```bash
cd <path-to-execution-framework>
uv run scripts/sync-routing.py --verify-versions --detail
```

Any mismatch between the registry version and a local version MUST be resolved
before the release is considered complete. Version drift that reaches `main`
is a blocking defect.

### 2.3 Dependency Declarations

If a module depends on other Astra ecosystem components, the `depends_on` field
MUST list each dependency with four pieces of information:

```yaml
  depends_on:
    - repo: alrcatraz/astra-<dependency>
      resource: <file path or API name>   # omit if the whole repo is the dependency
      required: <required|recommended|optional>
      reason: "<why this dependency exists>"
```

- `repo` — the GitHub repository name.
- `resource` — the specific file, API, or interface consumed.
- `required` — the severity of the dependency.
- `reason` — a plain-English explanation comprehensible to someone unfamiliar
  with the module's history.

### 2.4 Lifecycle Hooks

Lifecycle hooks generate dynamic checklist items in the `work-closure-check`
and `deploy-register` skills. They are declared in `registry.yaml` under a
`lifecycle` key and injected into the target SKILL.md files by the lifecycle
sync tool (see [Lifecycle Sync](#lifecycle-sync) below).

#### When to Add Hooks

Not every module needs lifecycle hooks. Use the following classification to
decide which hook types apply:

| Module characteristic | Closure hooks | Deploy hooks |
|:----------------------|:-------------:|:------------:|
| Has sub-modules or sub-skills that can drift out of sync | **SHOULD** | — |
| Has cross-repo dependencies (registry.yaml, external configs) | **SHOULD** | — |
| Modifies system state (services, configs, devices, firewall) | **SHOULD** | — |
| Requires setup beyond `git clone` (symlinks, DB init, env vars) | — | **SHOULD** |
| Runs as a daemon, server, or long-lived process | **SHOULD** | **SHOULD** |
| Needs health checks after deployment | — | **SHOULD** |
| Needs registration in service inventory | — | **SHOULD** |
| Is a pure documentation or reference module (no code, no state) | MAY omit | MAY omit |

Rules of thumb:

- If a module's correctness depends on external state (symlinks, devices,
  configuration files), add closure hooks to catch drift during wrap-up.
- If a module requires any action after `git clone` to become operational,
  add deploy hooks to formalise those actions as checklists.
- When unsure, prefer to add hooks. A checklist item that always passes is
  less harmful than a missing check that lets drift go undetected.

#### Closure Hooks

Checks that run when a task wraps up. These are injected into
`astra-skill-work-closure-check/SKILL.md`.

```yaml
  lifecycle:
    closure:
      - id: <unique-check-id>
        check: "<description of what to verify>"
        command: "<shell command, if applicable>"
        severity: <required|recommended|optional>
        trigger: "<condition that activates this hook>"
```

#### Deploy Hooks

Checks that run when the module is first deployed. These are injected into
`astra-skill-deploy-register/SKILL.md`.

```yaml
  lifecycle:
    deploy:
      - id: <unique-check-id>
        check: "<description of deployment verification>"
        severity: <required|recommended|optional>
        trigger: "<condition that activates this hook>"
```

#### Lifecycle Sync

After adding or modifying lifecycle hooks in `registry.yaml`, the developer
MUST run the lifecycle synchronisation tool to inject the hooks into the
target SKILL.md files:

```bash
cd <path-to-astra-aiagent-infra>
python3 lifecycle/astra-lifecycle-sync.py --update   # apply changes
python3 lifecycle/astra-lifecycle-sync.py --check    # preview only (dry run)
```

If the hooks are declared in `registry.yaml` but the corresponding
`LIFECYCLE_HOOKS_BEGIN` / `LIFECYCLE_HOOKS_END` block in the target SKILL.md
does not reflect them, the synchronisation step was skipped. This is a
non-blocking but SHOULD-fix issue.

---

## 3. Hub Index Update

Every module MUST be listed in the
[astra-hub](../skills/devops/astra-hub/SKILL.md) project index table.

The index exists in two copies:

| Copy | Location | Language | Audience |
|:-----|:---------|:---------|:---------|
| Public | `~/Projects/astra/astra-aiagent-infra/skills/devops/astra-hub/SKILL.md` | English | GitHub readers |
| Private | `~/.astra/repos/astra-aiagent-infra/skills/devops/astra-hub/SKILL.md` | Chinese | Local operator |

Both copies MUST be updated. Each entry MUST include:

- The module name (bold, linked if applicable)
- GitHub status (✅ / ❌ / fork indicator)
- Public development path
- Private workspace path (or — if not applicable)
- Purpose description
- Key files reference

The hub index is the primary navigation tool for the ecosystem. An unlisted
module is effectively invisible to anyone discovering the ecosystem through
the portal.

---

## 4. Execution Framework Routing

Skills that handle tasks classifiable by the
[execution-framework](../skills/execution-framework/SKILL.md)
SHOULD define a `routing.yaml` file at the module root. This file enables the
execution framework to suggest the right skill for a given task based on
keywords and indicators.

The `routing.yaml` MUST follow this format:

```yaml
version: 1

routing:

  - type: <task-category>
    label: "<human-readable label>"
    indicators:
      - <keyword>
      - <keyword>
    skills:
      - name: <hermes-skill-name>
    principles: "<guidance for how to use this skill>"
```

- `type` MUST be one of the categories defined in the execution framework's own
  routing table (`gpg-key-management`, `vcs-init`, `vcs-dev`, `vcs-release`,
  `vcs-sync`, etc.).
- `indicators` is a list of words or phrases that an agent might say when
  describing a task of this type.
- `skills` lists the Hermes skill name(s) to load when this routing entry
  matches.
- `principles` is a short instruction for the agent about how to apply this
  skill correctly.

Modules without a `routing.yaml` can still be loaded manually via
`skill_view(name='...')`, but the execution framework will not suggest them
automatically.

---

## 5. Version Management

### 5.1 Semantic Versioning

All Astra ecosystem components MUST use
[Semantic Versioning 2.0.0](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **MAJOR** — incompatible API or behavioural changes.
- **MINOR** — backward-compatible new functionality.
- **PATCH** — backward-compatible bug fixes.

### 5.2 Version Declarations

The version MUST be declared in every relevant metadata file (see
[§2.2 Version Consistency](#22-version-consistency)). All declarations MUST
agree. A module whose version declaration is out of step with `registry.yaml`
SHOULD NOT be released.

### 5.3 Local Modifications

Components deployed in a private workspace with local-only modifications MUST
append a `+local.<N>` suffix to the version (e.g., `1.0.0+local.1`). The
suffix MUST NOT appear in `registry.yaml`; the registry stores only the clean
canonical version.

### 5.4 Tags

Release versions MUST be tagged in git with `v<MAJOR.MINOR.PATCH>`
(e.g., `v1.0.0`). Tags are applied at milestone releases, not on every commit.

---

## 6. Deploy Integration

When a new module is first deployed (cloned, symlinked, or installed), the
`deploy-register` checklist applies. The developer MUST ensure that:

1. The module is recorded in the service inventory (`mgmt.services`).
2. Any deploy hooks declared in `registry.yaml` (see [§2.4](#24-lifecycle-hooks))
   are reflected in the `deploy-register` skill's `LIFECYCLE_HOOKS` section.
3. Health checks are configured if the module runs as a daemon, server, or
   long-lived process.
4. The module's configuration and credential requirements are documented
   (see `docs/credential-schema.md`).

---

## 7. Key Compliance Checks (Summary)

The following checks MUST pass before a module can be considered "registered
and compliant":

| # | Check | Source | Automated? |
|:-:|:------|:-------|:-----------|
| 1 | `README.md` exists with badge bar + bilingual structure | §1.1 | Manual |
| 2 | `SKILL.md` frontmatter contains all required keys | §1.2 | Manual |
| 3 | `LICENSE` file is present | §1.4 | Manual |
| 4 | `registry.yaml` entry exists with all required keys | §2.1 | `sync-routing.py --cron-check` |
| 5 | Version is consistent across registry + all local files | §2.2 | `sync-routing.py --verify-versions` |
| 6 | Lifecycle hooks are declared if needed, and synced | §2.4 | `astra-lifecycle-sync --check` |
| 7 | Hub index (both copies) has the module entry | §3 | Manual |
| 8 | `routing.yaml` exists (skills that need auto-suggestion) | §4 | `sync-routing.py --diff` |
| 9 | Git tag matches the registry version | §5.4 | Manual |

Items marked "Manual" have no automated check yet. Developers SHOULD verify
them during the closure checklist (see §6 of `work-closure-check`).

---

## 8. Glossary

| Term | Definition |
|:-----|:-----------|
| Closure hook | A lifecycle hook that runs during task wrap-up; see [§2.4](#24-lifecycle-hooks) |
| Deploy hook | A lifecycle hook that runs during first deployment; see [§2.4](#24-lifecycle-hooks) |
| Ecosystem registry | The `registry.yaml` file at the root of `astra-aiagent-infra` |
| Hub index | The `astra-hub` SKILL.md that lists all ecosystem projects |
| Lifecycle sync | The tool (`lifecycle/astra-lifecycle-sync.py`) that injects hooks from `registry.yaml` into target SKILL.md files |
| Execution framework | The routing system (`astra-skill-execution-framework`) that classifies tasks and suggests applicable skills |
