# Sync Timeout After E2EE Rebuild

> Diagnosis and fix for elevated Matrix sync timeout rates following a full E2EE device/crypto.db reset.

## Symptom

- Gateway responds to messages but with noticeably increased latency (user reports: "from sending to seeing your ack is much longer")
- Gateway log shows `sync error: ` (empty message) at regular ~70-second intervals
- Error is an `asyncio.TimeoutError` from the 45s `asyncio.wait_for` guard in `_sync_loop`
- Sync succeeds on ~50% of attempts, hangs for 45s on the other ~50%

## Distinguish From Other Sync Errors

| Pattern | Likely Cause |
|:--------|:-------------|
| Error has a message (`502`, `Cannot connect to host`, `Name or service not known`) | Server-side issue (Nginx/Synapse/DNS) |
| Error is **empty** (`sync error:  — retrying in 5s`) | Client-side TCP hang → `asyncio.wait_for` timeout |
| Errors are rare (<20/day) | Normal transient network glitches |
| Errors are **frequent (~70s apart)** + empty message | Network path instability |

## Root Cause

After an E2EE rebuild (new device ID + crypto.db reset), the Gateway's Matrix sync uses the **same public internet path** (Cloudflare → VPS-HK) as before, but the new E2EE device's sync requests behave differently enough to expose pre-existing **TCP half-open connection issues** on that path.

The `_sync_loop` code has a 45s `asyncio.wait_for` guard precisely for this reason:

```python
# From gateway/platforms/matrix.py ~line 1644
sync_data = await asyncio.wait_for(
    client.sync(since=next_batch, timeout=30000),  # server-side: 30s long-poll
    timeout=45.0,  # client-side: 45s max
)
```

When Cloudflare's CDN or the underlying TCP connection hangs (response never arrives), `asyncio.wait_for` raises `TimeoutError` after 45s, str(exc) = `''`. The sync loop sleeps 5s and retries.

## Diagnosis Steps

### 1. Quantify the problem

```bash
# Sync errors count by day
grep "sync error" ~/.hermes/logs/gateway.log | sed 's/,.*//' | sed 's/ .*//' | sort | uniq -c | sort -k2

# Pattern: before rebuild = ~9/day, after rebuild = 400-660/day
```

### 2. Rule out server-side causes

```bash
# Nginx proxy timeouts
ssh vps-hk 'grep -r "proxy_read_timeout\|proxy_connect_timeout" /etc/nginx/ 2>/dev/null'
# Should show 3600 (1 hour) — adequate for 30s long-poll sync

# Synapse resource health
ssh vps-hk 'systemctl is-active matrix-synapse && free -h | head -2 && uptime'

# Synapse log for sync-related errors
ssh vps-hk 'grep -i "sync\|timeout\|warn\|error" /var/log/matrix-synapse/homeserver.log 2>/dev/null | tail -20'
```

### 3. Compare network path latency

```bash
# Public path (via Cloudflare)
for i in 1 2 3; do
    T=$(curl -sk -o /dev/null -w '%{time_total}' --max-time 10 \ 
         https://matrix.gloriosa.space/_matrix/client/versions 2>/dev/null)
    echo "Cloudflare try $i: ${T}s"
done

# Overlay path (via EasyTier)
for i in 1 2 3; do
    T=$(curl -sk -o /dev/null -w '%{time_total}' -H "Host: matrix.gloriosa.space" \
         --max-time 10 https://10.20.4.10/_matrix/client/versions 2>/dev/null)
    echo "EasyTier try $i: ${T}s"
done
```

**Healthy baseline:** Cloudflare = ~7s, EasyTier = ~0.14s

### 4. Check Gateway TCP connections

```bash
ss -tnp | grep hermes | head -10
```

Watch for CLOSE-WAIT connections (half-closed sockets in the aiohttp pool).

## Fix: Route Through Overlay Network

The simplest and most effective fix is to bypass Cloudflare by routing `matrix.gloriosa.space` through the local overlay network:

### Option A (Preferred): `/etc/hosts` entry

```bash
# Replace 10.20.4.10 with VPS-HK's overlay IP
echo "10.20.4.10 matrix.gloriosa.space" | sudo tee -a /etc/hosts
```

This makes the Gateway connect to VPS-HK's Nginx directly via EasyTier:
- Latency drops from ~7s to ~0.14s (50x improvement)
- Sync hangs disappear entirely
- No Hermes config changes needed
- No Gateway restart required (DNS cache refreshes on next sync)

**Trade-off:** Loses Cloudflare DNS-based failover. If EasyTier is down, the Gateway can't reach the homeserver. The E2EE watchdog's dual-path redundancy (internal SSH + external HTTPS) covers this — if both paths fail, it alerts you.

### Option B: Adjust sync timeout (alternative, less effective)

Editable in Gateway source at `asyncio.wait_for timeout=45.0` — decreasing to 20s makes failures recover faster but doesn't fix the root cause.

## Verification

After the fix:

```bash
# 1. Verify sync error rate drops (wait 5-10 minutes)
grep -c "sync error" ~/.hermes/logs/gateway.log | tail -5

# 2. Verify latency improved
time curl -sk -o /dev/null -w '%{time_total}' \
  https://matrix.gloriosa.space/_matrix/client/versions 2>/dev/null

# 3. User perception: ask if response feels snappier
```

## Reference

- First diagnosed: 2026-06-09 during post-rebuild performance review
- Gateway `_sync_loop` implementation: `gateway/platforms/matrix.py` lines 1631-1705
- Pre-existing skill pitfall: _sync 长连接被 GFW 半挂_ — this is the same class of problem, now with a practical fix
