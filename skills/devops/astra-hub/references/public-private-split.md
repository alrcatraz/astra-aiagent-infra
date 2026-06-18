# Public/Private Workspace Split

> **Context:** Each astra-* project has a sanitised public copy (GitHub) and
> a private working copy with personal data overlays (`~/.astra/repos/`).
> Established 2026-06-17 to prevent leaking infrastructure details.

---

## Directory Structure

```
~/Projects/astra/<repo>/        ← Public: clean code, pushes to GitHub
  ├── scripts/
  ├── config/
  │   └── devices.yaml.example  ← Template only (no real data)
  ├── AGENTS.md
  └── README.md

~/.astra/
  ├── repos/<repo>/             ← Private: git clone from GitHub + overlays
  │   ├── config/
  │   │   └── devices.yaml      ← Real device IPs/SSH (in .gitignore)
  │   └── scripts/ (code from GitHub)
  ├── config/                   ← Shared personal configs
  │   ├── devices.yaml          ← Same file, backup copy
  │   └── format-convention.md  ← Personal notes (not for GitHub)
  ├── scripts/                  ← Personal scripts removed from public repo
  │   ├── diagnose.py
  │   └── diagnose.sh
  └── knowledge-base.db         ← Shared SQLite (lives outside repos)
```

## Setup Steps

### New Project (from scratch)

1. Create public repo at `~/Projects/astra/<repo>/` → `git init` → push to GitHub
2. `cd ~/.astra/repos && git clone https://github.com/alrcatraz/<repo>.git`
3. Add personal data files, then add to `.gitignore`:
   ```
   echo "config/devices.yaml" >> .gitignore
   echo ".env" >> .gitignore
   ```
4. Update Hermes config / cron jobs to point to `~/.astra/repos/<repo>/`

### Migration from Existing (like astra-sre)

1. Sanitise the public repo: remove personal data, rewrite as examples
2. Push sanitised code to GitHub
3. Clone into `~/.astra/repos/`
4. Restore personal data from git history (pre-sanitisation commits):
   ```
   cd ~/Projects/astra/<repo>/
   git show <last-clean-commit>:config/devices.yaml > ~/.astra/repos/<repo>/config/devices.yaml
   ```
5. Add personal files to `.gitignore` in private copy

### Fork Project (like Camofox)

1. Public copy remote setup:
   - `origin` → `alrcatraz/<fork-repo>` (your fork, push-enabled)
   - `upstream` → `original-owner/<original-repo>` (upstream, read-only)
2. Private copy remote: rename `origin` → `github` (avoids confusion)
3. `.gitignore` additions: `.env`, `config/*.json`

## Sync Workflow

```
# Pull code updates from GitHub into private copy:
cd ~/.astra/repos/<repo> && git pull github <branch>

# Push code changes to GitHub (from public copy):
cd ~/Projects/astra/<repo> && git push origin <branch>
```

Personal data files (`devices.yaml`, `.env`, custom scripts) are in
`.gitignore` — `git pull` will not overwrite them.

## Pitfalls

- **Don't work in `~/Projects/astra/` directly** — that copy has no personal
  data. Scripts referencing `config/devices.yaml` will fail.
- **Don't symlink `~/Projects/astra/<repo>/config/devices.yaml`** — a
  careless `git push` would upload real IPs. Copy the file manually.
- **Check `.gitignore` before `git add -A`** in the private copy — personal
  files should never be staged.
- **Fork repos need two remotes** — `origin` for your fork, `upstream` for
  the original. `git push` without specifying remote pushes to `origin`.
