# Astra Repo Publication Convention

> When deploying a new astra ecosystem repository to GitHub, verify these
> README elements before push. Missing badges or broken embeds are visible
> on the repo's GitHub landing page and affect first impressions.

## Required README Components

Every astra repo README must include these four elements:

| Element | Badge/Widget | Source |
|:--------|:-------------|:-------|
| License | `badgen.net/github/license/alrcatraz/<repo>` | Badgen |
| Stars | `badgen.net/github/stars/alrcatraz/<repo>` | Badgen |
| Last commit | `badgen.net/github/last-commit/alrcatraz/<repo>` | Badgen |
| Star history chart | `api.star-history.com/svg?repos=alrcatraz/<repo>&type=Date` | Star History |

Place badges in a subtitle line right after the `# Repo Name` heading:

```markdown
# astra-skill-example

> [![License](https://badgen.net/github/license/alrcatraz/astra-skill-example)](LICENSE)
> [![GitHub stars](https://badgen.net/github/stars/alrcatraz/astra-skill-example)](https://github.com/alrcatraz/astra-skill-example)
> [![GitHub last commit](https://badgen.net/github/last-commit/alrcatraz/astra-skill-example)](https://github.com/alrcatraz/astra-skill-example/commits)
```

## Star Chart Embed — Use Plain `<img>`, Not `<a><picture>`

**Verified working pattern (all devices, all markdown renderers):**

```markdown
<img alt="Star History Chart"
  src="https://api.star-history.com/svg?repos=alrcatraz/<repo>&type=Date"
  width="600" />
```

**Avoid the `<a><picture><source>` pattern** from star-history.com's default
embed code. It wraps the chart in a hyperlink and uses `<picture>` for
responsive dark/light mode switching. On many markdown renderers (including
GitHub), this renders the `alt` text as a clickable link instead of showing
the image. The simpler `<img>` tag works universally.

**MVCE:** This session's initial star chart embed used the `<a><picture>`
pattern and the user reported it showing as a hyperlink. Fixed by replacing
with plain `<img>` across 6 repos.

## Branch Naming Before First Push

When the GitHub repo was created via "Use this template", its default branch
is `main` (inherited from the template). But a local `git init` creates
`master`. **Check before pushing:**

```bash
# Check your local branch
git branch --show-current

# Check the remote's default
git ls-remote --symref origin HEAD
# → ref: refs/heads/main  HEAD   ← remote expects main
```

If they differ, rename locally and force-push:

```bash
git branch -m master main
git push -f origin main
git push origin --delete master   # remove stale branch
```

**MVCE:** 5 skill repos in this session were pushed as `master` while the
remote expected `main`, producing dual branches on GitHub. Caught by the
user after push, fixed with `git branch -m` + force push.
