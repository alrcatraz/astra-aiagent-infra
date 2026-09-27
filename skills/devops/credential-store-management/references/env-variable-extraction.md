# Bootstrap Env-File Variable Extraction Reference

## Reading a single variable from an env file

Read specific variables with `grep` — never `source` the file (it may pull in unwanted
state) and never bulk-read it into context (that dumps every secret).

```bash
# bare KEY=value files:
PW=$(grep '^KEY=' ~/.hermes/.env | cut -d= -f2-)

# quote-safe (strips surrounding single/double quotes if present):
PW=$(grep '^KEY=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//" | sed 's/^"//;s/"$//')
```

**Pitfall: grep pattern must match the file's actual style.** If lines are bare `KEY=`
(no `export` prefix), an `^export KEY=` grep silently returns empty — downstream
gpg/keepass calls then fail with confusing "Bad session key" / empty-password errors that
look like credential problems but are extraction bugs. Inspect the format once before
writing helpers against it.

## Credential lookup chain (role-based)

```
Need credential
  │
  ├─ Bootstrap layer (master passphrases: vault master, GPG key passphrase, sudo fallback)
  │    → read from the env file by name
  │
  ├─ Primary store (SSOT) — devices + services
  │    → KeePassXC backend : unlock with vault master, query keepassxc-cli / pykeepass
  │    → GPG-YAML backend : decrypt with GPG passphrase, parse YAML
  │    → pass(1) backend  : gpg-agent-cached, `pass show <path>`
  │
  └─ Not found anywhere → ask the user; NEVER fabricate or generate
```

**Key invariant:** the env file holds only the minimal bootstrap secrets needed to unlock
the stores. All device/service-specific secrets live in the SSOT — not in env files,
skills, or memory.
