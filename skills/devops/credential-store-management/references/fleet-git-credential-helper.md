# Fleet Git Credential Helper

`~/.hermes/scripts/git-credential-pass.sh` bridges git's credential protocol to
pass(1) entries at `git/https/<host>/<username>`. Handles github.com AND
git01.wrt.astra-lab.org (with or without :10443). Install as PRIMARY helper,
GCM last:

```bash
git config --global credential.helper "!$HOME/.hermes/scripts/git-credential-pass.sh"
git config --global --add credential.helper /home/alrcatraz/.dotnet/tools/git-credential-manager
```

## Pitfalls
- **TW .NET 10 breaks GCM** (verified 2026-09-16 SL0): the git-credential-manager
  dotnet tool is pinned to net8.0 runtime; TW ships only Microsoft.NETCore.App
  10.x → every HTTPS git op prints a .NET install error and falls back to
  interactive username/password. Fix is NOT installing .NET 8 — route credentials
  pass-first so GCM is never consulted for fleet hosts.
- After patching the canonical script, redeploy to machines that copied it
  earlier (SL0 keeps its own copy under ~/.hermes-scripts/).
- gpg-agent cache TTL on SL0 raised to 86400s (default-cache-ttl) so pass
  decrypts silently after the first unlock each day.
