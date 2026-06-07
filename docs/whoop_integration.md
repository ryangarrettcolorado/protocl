# WHOOP integration — setup guide (v3.8)

This is the operator playbook for going live with the WHOOP DataSource. Code is
already shipped — these are the **manual steps only you can do** to get your
own band's data flowing into Protocōl.

Total wall-clock: **~25 minutes** (longer than Oura because of WHOOP's OAuth
authorization-code flow), all free.

---

## Why WHOOP is harder than Oura

WHOOP doesn't offer a personal access token. Every WHOOP integration — even
single-user ones — has to go through a full OAuth 2.0 authorization-code dance
to mint a refresh token. The good news: you only do this once, then the
refresh token lasts indefinitely (until WHOOP invalidates it).

WHOOP also caps unapproved apps at **10 WHOOP members**. For Protocōl's
5-tester beta this is non-blocking; if you scale past 10 users you'll need to
submit the app for review (typical turnaround: a few days).

---

## 1. Register a developer app (5 min)

1. Go to <https://developer.whoop.com> and sign in with your WHOOP account
2. Click **Create New App** (top right)
3. Fill out the form:
   - **App name:** `Protocol` (or whatever you like — users see this on the
     consent screen)
   - **Contact email:** your email
   - **Privacy policy URL:** required even for development apps. If you don't
     have one yet, use `https://example.com/privacy` as a placeholder — WHOOP
     does not enforce its validity for unapproved apps under 10 users
   - **Redirect URIs:** add `http://localhost:8000/whoop/callback` (or wherever
     you'll run the one-time auth script — see step 3)
   - **Scopes:** check `offline`, `read:recovery`, `read:sleep`, `read:cycles`
4. Click **Create**
5. From the app detail page, copy the **Client ID** and **Client Secret**
   (the secret is shown once — save it somewhere safe immediately)

The `offline` scope is what makes long-lived refresh tokens possible. Without
it, WHOOP returns access-token-only responses that expire after 1 hour with
no way to renew.

---

## 2. Add the client credentials locally (1 min)

```bash
# ~/.zshrc or ~/.bashrc
export WHOOP_CLIENT_ID="paste-client-id"
export WHOOP_CLIENT_SECRET="paste-client-secret"
export WHOOP_LIVE="0"   # keep dormant until you've verified one round-trip
```

---

## 3. Run the one-time authorization flow (10 min)

WHOOP requires a browser-based consent step to mint your initial refresh
token. The simplest approach is a short ad-hoc script. Save the following as
`scripts/whoop_auth.py` in the repo:

```python
"""One-time WHOOP authorization-code flow.

Visit the printed URL, complete consent in your browser, paste the redirect
URL back into the terminal, and the script will print your refresh token.
"""
import os
import urllib.parse
import urllib.request
import urllib.error
import json

CLIENT_ID = os.environ["WHOOP_CLIENT_ID"]
CLIENT_SECRET = os.environ["WHOOP_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost:8000/whoop/callback"
SCOPES = "offline read:recovery read:sleep read:cycles"

# Step A: print the consent URL
auth_url = (
    "https://api.prod.whoop.com/oauth/oauth2/auth?"
    + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": "protocol-init",
        }
    )
)
print("1. Open this URL in your browser:\n")
print(auth_url)
print()

# Step B: paste the redirect URL after consenting
redirected = input(
    "2. After consenting you'll be redirected to localhost:8000 (which won't\n"
    "   load — that's expected). Paste the full redirect URL here:\n> "
).strip()
code = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query)["code"][0]

# Step C: exchange code for refresh token
data = urllib.parse.urlencode(
    {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
).encode()
req = urllib.request.Request(
    "https://api.prod.whoop.com/oauth/oauth2/token",
    data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"\nHTTP {e.code}: {e.read().decode()}")
    raise
print("\n--- SAVE THIS ---")
print(f"WHOOP_REFRESH_TOKEN={body['refresh_token']}")
```

Run it:

```bash
cd ~/protocl && source .venv/bin/activate && python scripts/whoop_auth.py
```

Copy the printed `WHOOP_REFRESH_TOKEN=…` line into your shell profile alongside
the client ID and secret.

---

## 4. Verify the integration is detected (1 min)

```bash
cd ~/protocl && source .venv/bin/activate && python
```

```python
>>> from protocl.modules.data_sources import registry
>>> whoop = registry()["whoop"]
>>> whoop.is_configured()
True
>>> whoop.is_live()
False   # OURA_LIVE-equivalent gate still off — good
```

If `is_configured()` returns `False`, your secrets aren't reaching the process.
Make sure you re-sourced your shell profile or restarted the terminal.

---

## 5. Smoke test against the live API (3 min)

Flip the live gate **just for this REPL** so it doesn't accidentally leak:

```bash
WHOOP_LIVE=1 python -c "
from datetime import date, timedelta
from protocl.modules.data_sources import registry
end = date.today()
start = end - timedelta(days=7)
result = registry()['whoop'].fetch_window(start, end)
print('status:', result.status)
print('records:', result.records_fetched)
print(result.frame.head())
"
```

Expected output: `status: OK`, a row count between 1 and 7, and a DataFrame
with the canonical wearables schema.

If you see `AUTH_ERROR`, the refresh token didn't take — re-run step 3. If
`RATE_LIMITED`, you're being throttled (WHOOP allows ~100 req/min per user);
wait 60 seconds and retry. If `UPSTREAM_ERROR`, check the error message — it
usually contains the upstream HTTP status.

---

## 6. Flip the live gate permanently (1 min)

Once the smoke test passes, update `WHOOP_LIVE` in your shell profile:

```bash
export WHOOP_LIVE="1"
```

Re-source your profile, restart any long-running processes (Streamlit dev
server, etc.), and you're live.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `is_configured() → False` | env vars not loaded | Re-source `~/.zshrc`, restart terminal |
| `AUTH_ERROR` on first call | Refresh token expired or revoked | Re-run step 3 |
| `RATE_LIMITED` | Too many requests | Wait 60 seconds; check for runaway scripts |
| Empty frame on `OK` | No WHOOP data in window | Verify wear-time on whoop.com for that window |
| `UPSTREAM_ERROR: token refresh returned HTTP 400` | Client ID/secret mismatch | Re-copy from developer.whoop.com |

---

## Scope upgrade path

If you later want strain or workout data, add the scope to your developer app
**and** update `WhoopDataSource.token_scope`, then re-run step 3 to mint a new
refresh token. WHOOP won't grant new scopes against an old refresh token.
