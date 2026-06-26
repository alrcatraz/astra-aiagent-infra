# `.env` Variable Extraction Reference

## Reading Variables from `~/.hermes/.env`

The `.env` file uses `export KEY=VALUE` format. Always use `grep` to read
specific variables — never `source ~/.hermes/.env` (it may pull in unwanted
state) and never `read_file` (it dumps the entire content to context).

### Simple Value (no quotes)

```bash
grep '^export KEY=' ~/.hermes/.env | cut -d= -f2-
```

### Single-quoted Value

```bash
grep '^export KEY=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//"
```

### Full Variable Extraction on One Line (quotes safe)

```bash
PW=$(grep '^export SUDO_PASSWORD=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//")
```

## Bootstrap Credential Lookup Chain

When automated scripts need credentials:

```
Need credential
  │
  ├─ Bootstrap secrets (GPG passphrase, KeePass master, sudo) → from .env
  │
  ├─ Device credentials (SSH/sudo for servers) →
  │   1. Read GPG_Key_Alrcatraz from .env
  │   2. Decrypt GPG YAML file
  │   3. Read target device info from YAML
  │
  └─ Website/app credentials →
      1. Read KEEPASS_PASSWORD from .env
      2. Query Combined.kdbx with keepassxc-cli
```

**Key invariant:** `.env` contains only the minimal bootstrap secrets to unlock
the other two layers. All device-specific secrets live in GPG-encrypted YAML.
