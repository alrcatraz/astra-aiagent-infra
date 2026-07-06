# Cross-Machine Git Bundle Transfer

> When the agent commits code on a machine without GitHub credentials, transfer the commits to the credential-holding machine via `git bundle` and push from there.
>
> 你的本地配置（HomeCentre01 地址、SSH 别名、密码）→ `work-closure-check/references/git-bundle-local-config.md`。

## When to Use

- You made git commits on a machine that doesn't have GitHub SSH keys, GCM credentials, or GPG-decryptable pass store entries
- The user expects you to push from the credential-holding machine, not from their personal device
- You have SSH access to the credential-holding machine and know the password

## Full Workflow

### Step 1: Create bundles on source machine

```bash
# For each repo with pending commits:
mkdir -p /tmp/git-bundles
git bundle create /tmp/git-bundles/<repo>.bundle HEAD --all
```

### Step 2: Transfer to HomeCentre01

```bash
sshpass -p '<jump-password>' scp /tmp/git-bundles/*.bundle <jump-user>@<jump-ip>:/tmp/
```

> `sshpass` must be installed on the source machine. If not, install with `zypper install sshpass` (openSUSE) or equivalent.

### Step 3: Apply bundles on HomeCentre01

When a branch is currently checked out, `git fetch` refuses to fetch into it directly. Use a temp-branch workaround:

```bash
sshpass -p '<jump-password>' ssh <jump-user>@<jump-ip> "
cd ~/Projects/astra/<repo>

# Fetch bundle into a temporary ref
git fetch /tmp/<repo>.bundle 'refs/heads/<branch>:refs/heads/bundle_<branch>'

# Switch to a temp branch so main/astra is free
git checkout -b _bundle_tmp

# Checkout the target branch and fast-forward merge
git checkout <branch>
git merge bundle_<branch> --ff-only

# Clean up temp refs
git branch -D _bundle_tmp bundle_<branch>
"
```

### Step 4: Push from HomeCentre01

Decrypt the GitHub PAT from the local pass store and push via HTTPS:

```bash
TOKEN=$(gpg --decrypt --pinentry-mode=loopback --passphrase '<gpg-passphrase>' \
  --quiet ~/.password-store/git/https/github.com/<github-user>.gpg 2>/dev/null | head -1)

GIT_TERMINAL_PROMPT=0 git -c credential.helper="!f() { echo username=<github-user>; echo password=$TOKEN; }; f" push origin <branch>
```

> The `--pinentry-mode loopback` flag allows GPG decryption without a TTY/pinentry dialog — critical for non-interactive SSH sessions.

## Pitfalls

1. **`git fetch` refuses to fetch into checked-out branch.** Always use the temp-branch workaround (Step 3). A simple `+main:main` refspec is not enough — git rejects it by design.

2. **`gpg-preset-passphrase` is not always available.** On some machines this binary is missing (it's an optional component of `gnupg`). When it is available, it may return "Not implemented" if `allow-preset-passphrase` is not set in `gpg-agent.conf`. Stick with `--pinentry-mode loopback` for reliability.

3. **Bundle size is proportional to commit count, not file changes.** A bundle includes the full commit tree and blobs. For repos with many files (e.g. 36KB README-only change → 17KB bundle), this is negligible.

4. **Credentials are in the shell command history.** The PAT appears in the credential.helper inline string. This is ephemeral (SSH session ends), but be aware of it. The pass store entry itself is encrypted.

5. **`GIT_TERMINAL_PROMPT=0` prevents interactive auth fallback.** If the credential helper fails, git won't prompt for a password. This ensures clean failure instead of a hung SSH session.

6. **HomeCentre01 password may differ from the GPG passphrase.** These are stored as separate secrets — see the local config file for specific values.

## Verification

After pushing, verify on the source machine that `git status` is clean and the remote matches local:

```bash
git fetch origin
git log --oneline origin/<branch>..<branch>
# Should be empty (no unpushed commits)
```
