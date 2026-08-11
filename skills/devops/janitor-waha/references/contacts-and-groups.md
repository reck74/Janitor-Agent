# Contacts and Groups — extraction playbook

Reference for the WAHA classes of API that involve reading **contacts**, **groups**,
and their **participants**. Documented through the Aug 2026 large-group audit on
the workstation, where the goal was a 225-row participant table.

> **Synthetic examples only.** All phone numbers, group IDs, LIDs, usernames, and
> contact names in this file are illustrative placeholders (e.g. `573001234567`,
> `120363000000000000@g.us`, `Maria Example`). Replace with real values from your
> own WAHA session before applying.

## TL;DR

Two completely different APIs:

| Need | Endpoint | NOWEB store required? | Latency |
|------|----------|-----------------------|---------|
| List groups you're in | `GET /api/{session}/groups` | **No** | Instant |
| List participants of a group | `GET /api/{session}/groups` (same call) | **No** | Instant |
| Participant phone number / LID / admin role | same response | **No** | In the group record |
| Participant `pushName` / `businessName` / `verifiedName` | `GET /api/{session}/contacts/all` | **YES** | First sync: 1–5 min |
| Per-participant detail lookup | `GET /api/contacts/{id}` | **YES** | First sync: 1–5 min |

The **groups endpoint already gives you id + phoneNumber + username + admin**
without NOWEB store. You only need NOWEB store if you want richer profile data
(name, businessName, profile pic URL).

## Group listing + participants (no store required)

```bash
WAHA_API_KEY=$(grep '^WAHA_API_KEY=' ~/.janitor/docker/waha.env | cut -d= -f2)

curl -s -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/default/groups \
  -o /tmp/waha-groups.json
```

Returns a **dict keyed by groupId**, not a list:

```json
{
  "120363000000000001@g.us": {
    "id": "120363000000000001@g.us",
    "addressingMode": "lid",
    "subject": "Example Large Group",
    "subjectOwnerPn": "573001111111@s.whatsapp.net",
    "subjectTime": 1785634376,
    "size": 225,
    "creation": 1785634376,
    "ownerPn": "573001111111@s.whatsapp.net",
    "owner_country_code": "CO",
    "announce": true,
    "isCommunity": false,
    "participants": [
      {"id": "61800000000001@lid",
       "phoneNumber": "573001222222@s.whatsapp.net",
       "admin": null}
    ]
  }
}
```

**Per-participant fields observed** (Aug 2026, NOWEB engine):
- `id` (LID format `XXXXX@lid`) — always present
- `phoneNumber` (`57XXXXXXXXXX@s.whatsapp.net`) — 81% of contacts
- `username` (handle `@xxx`) — 19%, mostly business accounts
- `admin` (`superadmin` | `admin` | `null`) — always present

**Search logic that works**:

```python
matches = []
for gid, g in groups.items():
    subj = g.get('subject', '').lower()
    score = sum(k in subj for k in ['example', 'august', 'group', 'main'])
    if score > 0:
        matches.append((score, gid, g))
matches.sort(key=lambda x: -x[0])
```

## Enriching with pushName / businessName / verifiedName (NOWEB store required)

If the user wants more than `phoneNumber + admin`, you need the NOWEB store.
Without it, `/api/{session}/contacts/all` returns `200 OK` with a **zero-byte body**,
and individual `/api/contacts/{id}` lookups return `404` even for contacts
visible in groups.

### Critical gotcha 1: snake_case vs camelCase

WAHA's NOWEB store config field is **`fullSync` (camelCase)**, not `full_sync`.
If you send snake_case, WAHA silently accepts it but stores `fullSync: false`
and you get a partial / no sync.

Verified Aug 2026 — sending `{"noweb":{"store":{"enabled":true,"full_sync":true}}}`
resulted in `store.fullSync: false` in the echoed config. The correct payload is
`{"noweb":{"store":{"enabled":true,"fullSync":true}}}`.

### Critical gotcha 2: Update endpoint is PUT, not POST

`POST /api/sessions/{name}` returns 404. The correct update endpoint is
**`PUT /api/sessions/{name}`** (verified against
`https://raw.githubusercontent.com/devlikeapro/waha/core/src/api/sessions.controller.ts`).

### Critical gotcha 3: Restart does NOT re-sync

If you update an already-authenticated session to enable NOWEB store, the engine
**skips history sync on reconnection**. Logs show:

```
NOWEBEngine: Reconnection with existing sync data, skipping history sync wait.
Transitioning to Online.
```

To actually populate the contact store, you must:

1. Logout (unlink device)
2. Delete the session
3. Re-create with `config.noweb.store.enabled=true` AND `fullSync=true`
4. Re-pair via QR or pairing code
5. Wait 1–5 minutes for initial sync to complete

Without fresh pairing, the store stays empty even though `enabled=true`.

### Critical gotcha 4: Sync takes time after WORKING

`session.status = WORKING` does NOT mean contacts are ready. Watch for these
log lines that confirm sync progress:

```
INFO  NOWEBEngine: clean dirty bits account_sync
INFO  NowebPersistentStore: got update for non-existent contact. update: '{"id":"X@lid","notify":"Name"}'
```

The "non-existent contact" warnings are NORMAL during sync — they mean WAHA is
receiving updates from the WhatsApp server about contacts that haven't been
written to the persistent store yet. Sync is done when these warnings stop
appearing.

**Probe sync progress**:

```bash
curl -s -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/default/contacts/all | wc -c
# 0 bytes = not synced yet
# >0 bytes (JSON array) = synced, count = len(json.loads(...))
```

### Correct sequence to enable NOWEB store from scratch

```bash
WAHA_API_KEY=$(grep '^WAHA_API_KEY=' ~/.janitor/docker/waha.env | cut -d= -f2)

# Step 1: Clean slate
curl -s -X POST -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/sessions/default/stop > /dev/null
sleep 2
curl -s -X POST -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/sessions/default/logout > /dev/null
sleep 2
curl -s -X DELETE -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/sessions/default > /dev/null
sleep 2

# Step 2: Create session WITH store config from the start
curl -s -X POST -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"default","config":{"engine":"NOWEB","noweb":{"store":{"enabled":true,"fullSync":true}}}}' \
  http://127.0.0.1:3000/api/sessions

# Step 3: Start + pair (QR or pairing code)
curl -s -X POST -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/sessions/default/start
# ... pair the device ...

# Step 4: Wait for WORKING
for i in $(seq 1 30); do
  status=$(curl -s -H "X-Api-Key: $WAHA_API_KEY" \
    http://127.0.0.1:3000/api/sessions/default | \
    python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))")
  [ "$status" = "WORKING" ] && break
  sleep 2
done

# Step 5: Wait for sync to populate (poll until >0 bytes)
for i in $(seq 1 60); do
  bytes=$(curl -s -H "X-Api-Key: $WAHA_API_KEY" \
    http://127.0.0.1:3000/api/default/contacts/all | wc -c)
  echo "[${i}x5s] $bytes bytes"
  [ "$bytes" -gt 50 ] && break
  sleep 5
done
```

## Update an existing authenticated session (no re-pairing)

If the user does NOT need contact enrichment and just wants to add/change session
config (e.g. NOWEB store toggle for future syncs):

```bash
WAHA_API_KEY=$(grep '^WAHA_API_KEY=' ~/.janitor/docker/waha.env | cut -d= -f2)

# Stop session
curl -s -X POST -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/sessions/default/stop > /dev/null
sleep 2

# Update config via PUT (NOT POST)
curl -s -X PUT -H "X-Api-Key: $WAHA_API_KEY" -H "Content-Type: application/json" \
  -d '{"config":{"engine":"NOWEB","noweb":{"store":{"enabled":true,"fullSync":true}}}}' \
  http://127.0.0.1:3000/api/sessions/default | python3 -m json.tool

# Restart — will NOT re-sync (see Gotcha 3), but session comes back online
curl -s -X POST -H "X-Api-Key: $WAHA_API_KEY" \
  http://127.0.0.1:3000/api/sessions/default/start
```

Session comes back online in ~5s (no re-pairing needed because credentials
persist in the bind-mounted `/app/.sessions` directory).

## Endpoint reference (contacts/groups)

| Endpoint | Method | Returns | Store needed |
|----------|--------|---------|--------------|
| `/api/{session}/groups` | GET | All groups + participants | No |
| `/api/{session}/groups/{id}` | GET | Single group + participants | No |
| `/api/{session}/contacts/all` | GET | Full contact list (after sync) | **Yes** |
| `/api/{session}/contacts?session=...` | GET | Various filters | **Yes** |
| `/api/contacts/{id}` | GET | Single contact detail | **Yes** |
| `/api/{session}/contact/{phoneNumber}` | GET | Phone lookup | **Yes** |

**`addressingMode: "lid"`** (LID = Local Identifier, WhatsApp's privacy-preserving
internal ID) is now the default for most accounts. The `phoneNumber` field still
resolves the real number via the `xxx@s.whatsapp.net` suffix. The `lid` field
shows the internal ID — never share that externally.

## Field names reference (Aug 2026 / NOWEB store populated)

From a single contact record:

```json
{
  "id": "61800000000001@lid",
  "name": "Example Contact (from address book)",
  "pushName": "Display Name in WhatsApp",
  "shortName": "Short Name",
  "phoneNumber": "573001222222@s.whatsapp.net",
  "verifiedName": "Official Verified Business Name",
  "businessName": "Business Profile Name",
  "isBusiness": true,
  "profilePicUrl": "https://...",
  "isContact": true,
  "isUser": true,
  "isGroup": false,
  "isMe": false
}
```

**`verifiedName` and `businessName`** are only present for WhatsApp Business
accounts with a verified green checkmark or a business profile. Most participants
won't have these — that's normal, not a bug.

## Sanitization note

When you apply these recipes against your own session, expect real phone numbers
in the `573000000000` / `573009999999` ranges (or whatever country you operate in),
real group JIDs from `120363...@g.us`, real LIDs in `XXXXX@lid`, and real
display names. Replace the placeholder values shown here before pasting examples
into commit messages, public docs, or shared runbooks.
