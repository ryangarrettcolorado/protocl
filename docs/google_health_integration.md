# Google Health integration — setup guide (v3.8)

This is the operator playbook for going live with the Google Health DataSource,
which is the post-September-2026 replacement for the Fitbit Web API. Code is
already shipped — these are the **manual steps only you can do** to get your
own Fitbit or Pixel Watch data flowing into Protocōl.

Total wall-clock: **~30 minutes** (Google Cloud Console is the slowest part),
all free.

---

## Why Google Health and not Fitbit Web API

In **September 2026**, Google shuts down the legacy Fitbit Web API and
migrates every Fitbit and Pixel Watch user to the unified Google Health API,
authenticated via standard Google OAuth 2.0. We build directly against the new
API — every line of code targeting legacy endpoints would need to be rewritten
within months.

Coverage is the same (sleep, heart rate, HRV, activity, etc.); the auth flow
and payload shape are new.

Source: <https://developers.google.com/health/about>

---

## 1. Migrate your Fitbit account to a Google account (5 min)

If you signed up for Fitbit before 2023, your account may still be on the
legacy Fitbit auth system. Confirm at <https://www.fitbit.com/global/us/google>
— if you see a "Move to Google" prompt, follow it. Until you've migrated,
Google Health API calls return empty data even with valid credentials.

Pixel Watch users skip this step (you're already on Google auth).

---

## 2. Create a Google Cloud project + OAuth client (15 min)

1. Go to <https://console.cloud.google.com> and create a new project
   - Name: `Protocol Health` (or similar)
2. Enable the Google Health API
   - Navigation: **APIs & Services → Library**
   - Search for "Health API" and click **Enable**
   - Note: as of early 2026 this API is still rolling out; if you don't see
     it, you may need to join Google's developer preview at
     <https://developers.google.com/health/get-started>
3. Configure the OAuth consent screen
   - Navigation: **APIs & Services → OAuth consent screen**
   - User type: **External** (unless you have a Workspace org)
   - App name: `Protocol`
   - User support + developer email: your email
   - Authorized domains: leave blank for development
   - Scopes: add the three Health API scopes:
     - `.../auth/health.sleep.read`
     - `.../auth/health.heartrate.read`
     - `.../auth/health.activity.read`
   - Test users: add your own Google email (required for unverified apps)
   - Click **Save and Continue** through all sections
4. Create OAuth credentials
   - Navigation: **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Name: `Protocol — local development`
   - Authorized redirect URIs: `http://localhost:8000/google/callback`
   - Click **Create**
5. Copy the **Client ID** and **Client Secret** from the popup (the secret can
   be re-shown later via the same Credentials page)

---

## 3. Add the client credentials locally (1 min)

```bash
# ~/.zshrc or ~/.bashrc
export GOOGLE_HEALTH_CLIENT_ID="paste-client-id"
export GOOGLE_HEALTH_CLIENT_SECRET="paste-client-secret"
export GOOGLE_HEALTH_LIVE="0"   # keep dormant until you've verified one round-trip
```

---

## 4. Run the one-time authorization flow (5 min)

Save as `scripts/google_health_auth.py`:

```python
"""One-time Google Health authorization-code flow.

Visit the printed URL, complete consent in your browser, paste the redirect
URL back into the terminal, and the script will print your refresh token.
"""
import os
import urllib.parse
import urllib.request
import urllib.error
import json

CLIENT_ID = os.environ["GOOGLE_HEALTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_HEALTH_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost:8000/google/callback"
SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/health.sleep.read",
        "https://www.googleapis.com/auth/health.heartrate.read",
        "https://www.googleapis.com/auth/health.activity.read",
    ]
)

# Step A: print the consent URL
auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "access_type": "offline",       # ← required to get a refresh token
            "prompt": "consent",            # ← required to re-issue a refresh token
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
    "https://oauth2.googleapis.com/token",
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
print(f"GOOGLE_HEALTH_REFRESH_TOKEN={body['refresh_token']}")
```

The `access_type=offline` and `prompt=consent` parameters are **both required**.
Without `offline`, Google returns access tokens only. Without `prompt=consent`,
Google won't re-issue a refresh token on subsequent runs (Google only mints
refresh tokens on first consent unless the prompt is forced).

Run it:

```bash
cd ~/protocl && source .venv/bin/activate && python scripts/google_health_auth.py
```

Copy the printed `GOOGLE_HEALTH_REFRESH_TOKEN=…` line into your shell profile.

---

## 5. Verify the integration is detected (1 min)

```bash
cd ~/protocl && source .venv/bin/activate && python
```

```python
>>> from protocl.modules.data_sources import registry
>>> gh = registry()["google_health"]
>>> gh.is_configured()
True
>>> gh.is_live()
False
```

---

## 6. Smoke test against the live API (3 min)

```bash
GOOGLE_HEALTH_LIVE=1 python -c "
from datetime import date, timedelta
from protocl.modules.data_sources import registry
end = date.today()
start = end - timedelta(days=7)
result = registry()['google_health'].fetch_window(start, end)
print('status:', result.status)
print('records:', result.records_fetched)
print(result.frame.head())
"
```

Expected: `status: OK` and a row count matching your wear-time in the window.

If you see `AUTH_ERROR`, the refresh token is wrong or the Health API is not
enabled on your Cloud project. If `UPSTREAM_ERROR`, check the error message —
during the API preview period, some scopes return 404 if your account isn't
yet enrolled.

---

## 7. Flip the live gate permanently (1 min)

```bash
export GOOGLE_HEALTH_LIVE="1"
```

Re-source your profile and you're live.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `is_configured() → False` | env vars not loaded | Re-source `~/.zshrc`, restart terminal |
| `AUTH_ERROR` immediately | refresh token didn't get minted (missing `access_type=offline` or `prompt=consent`) | Re-run step 4, verify both flags |
| `AUTH_ERROR` after working previously | Refresh token revoked (most often: you ran the auth flow without `prompt=consent` on a re-auth) | Re-run step 4 |
| Empty frame on `OK` for a Fitbit user | Fitbit-to-Google migration not complete | Visit <https://www.fitbit.com/global/us/google> |
| `UPSTREAM_ERROR: returned HTTP 404` | Health API not enabled, or your account isn't enrolled in the preview | Re-check **APIs & Services → Library** in Cloud Console |
| `UPSTREAM_ERROR: returned HTTP 403` | Test-user list doesn't include your account | Add your email under **OAuth consent screen → Test users** |

---

## Production cutover (post-September-2026)

When Google fully decommissions the legacy Fitbit Web API in September 2026:

1. Existing Fitbit users on this integration: **no code changes required** —
   the refresh tokens you minted in 2026 continue to work
2. Existing Fitbit Web API users (not on Protocōl): the migration prompt
   appears in their Fitbit app
3. Pixel Watch users: were always on Google Health auth — unaffected

If Google publishes revised scope names closer to the cutover, update
`GoogleHealthDataSource.token_scope` and re-mint refresh tokens.
