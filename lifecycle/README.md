# Lifecycle Hook Sync

Auto-generates ecosystem lifecycle checklists in skill SKILL.md files.
Part of [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra).

## How It Works

Components in `registry.yaml` declare lifecycle hooks that describe what to
verify or act upon during specific lifecycle events (e.g. task closure or
service deployment). The sync tool reads these declarations and injects them
into the corresponding SKILL.md files as structured checklists.

```
registry.yaml            astra-lifecycle-sync.py
  │                              │
  │  lifecycle:                  │
  │    closure: [...]  ──────────┤
  │    deploy:  [...]  ──────────┤
  │                              │
  │                     ┌────────┴────────┐
  │                     ▼                 ▼
  │           work-closure-        deploy-register/
  │           check/SKILL.md       SKILL.md
  │           ┌─────────────┐     ┌─────────────┐
  │           │  Ecosystem  │     │  Ecosystem  │
  │           │  Hooks      │     │  Hooks      │
  │           │  (auto-gen) │     │  (auto-gen) │
  │           └─────────────┘     └─────────────┘
  └───────────────────────────────────────────
```

## Usage

```bash
# Update all SKILL.md files with current lifecycle hooks
python3 lifecycle/astra-lifecycle-sync.py

# Same, explicit
python3 lifecycle/astra-lifecycle-sync.py --update

# Dry-run: check if any SKILL.md is out of sync
python3 lifecycle/astra-lifecycle-sync.py --check
```

Exit code: `0` = clean, `1` = out of sync (or error).

## Pre-commit Hook

The pre-commit hook (installed via `--install-hook`) runs `--check`
on every commit to this repository. If SKILL.md files are out of sync,
the commit is blocked with instructions to run `--update` first.

Install it once:

```bash
python3 lifecycle/astra-lifecycle-sync.py --install-hook
```

## Adding Lifecycle Hooks to a New Component

To make a component participate in lifecycle hooks, add a `lifecycle`
section to its entry in `registry.yaml`:

```yaml
- type: sre
  name: my-component
  lifecycle:
    closure:
      - id: my-check
        check: "Describe what to verify"
        command: "cd $MY_DIR && tool --flag"
        severity: required     # required | recommended | optional
        trigger: "when to run this check"
    deploy:
      - id: my-deploy-check
        check: "Describe what to register or configure"
        severity: required
        trigger: "when this check applies"
```

Then run `astra-lifecycle-sync --update` to propagate.

## Convention

- `closure` hooks → injected into `astra-skill-work-closure-check/SKILL.md`
- `deploy` hooks  → injected into `astra-skill-deploy-register/SKILL.md`

The injected block is delimited by `<!-- LIFECYCLE_HOOKS_BEGIN -->` and
`<!-- LIFECYCLE_HOOKS_END -->` markers. **Do not edit the block manually** —
modify `registry.yaml` and re-run the sync tool instead.
