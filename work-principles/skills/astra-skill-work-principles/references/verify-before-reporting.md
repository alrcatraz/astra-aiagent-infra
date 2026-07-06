# Verify Before Reporting — Reference

> Origin session: work-principles refactor (2026-07-04)
> Pattern: agent repeatedly claimed "done" for work that was not actually verified.

## Verification Table

| You said "done" for | But actually | Lesson |
|:--------------------|:-------------|:-------|
| Files written | File didn't exist on disk | Read back every write: `cat`, `ls -la`, `head` |
| Directories deleted | Still existed | Confirm with `ls: cannot access` |
| Plugin working | Hook failed silently | Check `grep plugin agent.log` — silent failure ≠ success |
| SSHFS mounted | Wrong target IP | Verify `ip -br addr show` on BOTH machines first |
| Skill created | Not in Hermes registry | Check `skills_list()` *after* creation |
| Environment baseline location | "It's lost / not covered" | Check the tutorial docs — it was in `change-safeguard` all along |
| Repo name | Used informal label ("umbrella") | Check actual GitHub repos — use exact names |
| Plugin override working | Assumed dispatch_tool works from handler | Verify with `hermes chat -q` test — capture real tool output |
| Component structure | Assumed standards are met | Run full audit against Module Development Guide — badge bars, bilingual, SKILL frontmatter, LICENSE, AGENTS.md, routing.yaml, registry, hub |
| Repo existence | Assumed there is/isn't a repo | Check `~/Projects/astra/`, GitHub API, `.astra/repos/` — all three before stating |

## Recovery Protocol

When the user corrects you twice in a row on the same error class:
1. Stop all modifications immediately
2. Present: what's done (proven), pending, uncertain
3. Ask for confirmation before continuing
