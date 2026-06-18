#!/usr/bin/env python3
"""
Quick crypto state check — no Matrix client needed.
Reads crypto.db directly via SQLite3.
Safe to run while Gateway is active (read-only, no conflict).
"""
import sqlite3, os, sys
from pathlib import Path
from datetime import datetime

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
DB = HERMES_HOME / "platforms" / "matrix" / "store" / "crypto.db"

if not DB.exists():
    print(f"crypto.db not found at {DB}")
    sys.exit(1)

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

print("=== Outbound Megolm Sessions ===")
rows = cur.execute("""
    SELECT room_id, session_id, shared, max_messages, message_count, created_at
    FROM crypto_megolm_outbound_session
    ORDER BY room_id
""").fetchall()
if rows:
    for r in rows:
        room = r[0]
        if "fjNpoF" in room:
            name = "DM"
        elif "HNjfC" in room:
            name = "Home"
        elif "OEYma" in room:
            name = "Other"
        else:
            name = room[:8]
        created = datetime.fromisoformat(str(r[5]).replace("T", " "))
        age_secs = (datetime.now() - created).total_seconds()
        print(f"  {name:<5} session={r[1][:20]}... shared={r[2]} msgs={r[4]}/{r[3]} age={age_secs:.0f}s")
else:
    print("  (none — Gateway hasn't created sessions yet)")

print()
print("=== Inbound Megolm Sessions ===")
count = cur.execute("SELECT COUNT(*) FROM crypto_megolm_inbound_session").fetchone()[0]

# Check who the inbound sessions come from (bot vs user devices)
rows = cur.execute("SELECT sender_key FROM crypto_megolm_inbound_session").fetchall()
bot_key = "obTdrkw8rWz"  # bot's identity key prefix
bot_inbound = sum(1 for r in rows if str(r[0]).startswith(bot_key))
user_inbound = count - bot_inbound
print(f"  Total: {count}")
print(f"  From bot (self): {bot_inbound}")
print(f"  From user devices: {user_inbound}")
if count > 0 and user_inbound == 0:
    print("  ** All inbound sessions are from bot's own key!")
    print("     -> User's encrypted messages cannot be decrypted.")
    print("     -> Possible causes:")
    print("        1. DecryptionDispatcher not registered in Gateway")
    print("        2. Key request rejected by user Element (device untrusted)")
    print("        3. crypto_account.sync_token is empty (affects to-device sync)")

print()
print("=== Account ===")
try:
    acct = cur.execute("SELECT device_id, shared FROM crypto_account").fetchone()
    if acct:
        print(f"  device_id={acct[0]}, account.shared={acct[1]}")
        if acct[1] == 0:
            print("  ** Account NOT shared yet!")
except Exception:
    # Fallback for if table name differs
    for tbl in ["crypto_account", "e2e_account"]:
        try:
            acct = cur.execute(f"SELECT device_id, shared FROM {tbl}").fetchone()
            if acct:
                print(f"  (from {tbl}) device_id={acct[0]}, account.shared={acct[1]}")
                break
        except Exception:
            continue

print()
print("=== Sync Token ===")
try:
    cur.execute("SELECT sync_token FROM crypto_account LIMIT 1")
    token = cur.fetchone()
    exists = bool(token and token[0])
    print(f"  sync_token present: {exists}")
    if exists and token[0]:
        print(f"  sync_token length: {len(token[0])} chars")
    else:
        print("  ** sync_token is empty — may affect to-device sync")
except Exception as e:
    print(f"  sync_token check failed: {e}")

conn.close()
