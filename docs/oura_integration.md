# Oura integration — setup guide (v3.8)

This is the operator playbook for going live with the Oura DataSource. Code is
already shipped — these are the **manual steps only you can do** to get your
own ring's data flowing into Protocōl.

Total wall-clock: **~10 minutes**, all free.

---

## 1. Generate a Personal Access Token (3 min)

1. Sign in at <https://cloud.ouraring.com> with the same account your ring is paired to
2. Click your initials (top right) → **Account Settings**
3. Navigate to **Personal Access Tokens** in the left sidebar
   - Direct link: <https://cloud.ouraring.com/personal-access-tokens>
4. Click **Create New Personal Access Token**
5. Give it a name like `Protocol App — local + Streamlit`
6. Copy the generated token immediately (you cannot see it again after closing
   the dialog — Oura shows it once)

The token is a long opaque string (~32+ characters). Treat it like a password.

---

## 2. Add the secret locally (2 min)

For local development, drop the PAT into your shell environment so pytest
runs and ad-hoc scripts can reach it:

```bash
# Add to ~/.zshrc or ~/.bashrc, then `source` it
export OURA_PAT="paste-your-token-here"
export OURA_LIVE="0"   # keep dormant until you've verified one round-trip
```

`OURA_LIVE=0` is the safety gate. The DataSource will detect a configured PAT
but refuse to make real API calls until you flip it to `1`. This lets you
verify the secret is loaded correctly before any network traffic happens.

---

## 3. Verify the integration is detected (1 min)

Open a Python REPL in the `protocl_demo` directory:

```bash
cd ~/protocl && source .venv/bin/activate && python
```

```python
from protocl.modules.data_sources import registry
src = registry()["oura"]

print(src.is_configured())   # True if your PAT loaded
print(src.is_live())         # False (gate is still off)

src.validate_config()        # silently passes if PAT looks valid
```

If `is_configured()` returns `False`, your shell hasn't picked up the env var
— re-source your rc file or open a new terminal.

---

## 4. First live fetch (2 min)

Flip the live gate and pull a one-week window:

```bash
export OURA_LIVE=1
python
```

```python
from datetime import date, timedelta
from protocl.modules.data_sources import registry

src = registry()["oura"]
result = src.fetch_window(date.today() - timedelta(days=7), date.today())

print(result.status)            # FetchStatus.OK
print(result.records_fetched)   # ~7
print(result.frame.head())      # canonical wearables schema
```

A successful first call confirms:

- Your PAT is valid
- The merge of `daily_sleep` + `daily_readiness` works for your account
- The schema mapper produces the expected columns

If you get `FetchStatus.AUTH_ERROR`, the PAT is bad — regenerate it and try
again. If `FetchStatus.RATE_LIMITED`, you've hit Oura's 300-req/min cap;
unlikely on a single call, but wait 60 seconds and retry.

---

## 5. Add the secret to Streamlit Cloud (3 min)

For the deployed beta, add the same PAT to Streamlit Cloud secrets:

1. Open <https://share.streamlit.io/> and select the `protocl_demo` app
2. Click **Settings** → **Secrets**
3. Add these two lines:

   ```toml
   OURA_PAT = "paste-your-token-here"
   OURA_LIVE = "1"
   ```

4. Click **Save**. Streamlit Cloud auto-restarts the app

---

## 6. (Optional) Wire into the sync orchestrator

The `DataSource` registry is now available to `sync_orchestrator.py`. To add
Oura to the per-user automated sync rotation, follow the pattern in
`SOURCES = ("strava", "apple_health")` and add a runner that calls:

```python
result = registry()["oura"].fetch_window(start, end)
if result.ok:
    # merge result.frame into the user's wearables.csv
    ...
```

This wiring is deferred until you've confirmed the live fetch works for at
least your own account. There's no rush — the DataSource works fine as a
standalone module today.

---

## Multi-user note

The current implementation uses a **single shared PAT** stored in
Streamlit secrets. This is correct for the owner's data but **does not scale**
to beta testers who each have their own Oura account.

For multi-user support (Phase 2), the path is:

1. Register a real **OAuth 2.0 app** at <https://cloud.ouraring.com/oauth/applications>
2. Add an `OuraOAuthDataSource` subclass that accepts `client_id` +
   `client_secret` + per-user `refresh_token`
3. Store per-user refresh tokens in `ProfileStorage` under each profile

The `DataSource` ABC already supports this — `OuraOAuthDataSource` would
simply override `is_configured()` to check for the user's refresh token in
their profile directory rather than reading a global env var. No changes
needed to the base class.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `is_configured()` returns False | PAT not in env or too short | Re-export `OURA_PAT`, confirm length ≥ 20 |
| `is_live()` returns False | `OURA_LIVE` not set or set to `0` | `export OURA_LIVE=1` |
| `FetchStatus.AUTH_ERROR` | PAT is invalid, expired, or revoked | Regenerate at cloud.ouraring.com |
| `FetchStatus.RATE_LIMITED` | Hit 300/min cap | Wait 60s, retry |
| `FetchStatus.UPSTREAM_ERROR` with "requests not installed" | Optional dep missing | `pip install requests` (already in requirements.txt) |
| Empty frame, status OK | Account has no Oura data in window | Check the date range; Oura requires data to be synced from the ring first |

---

## Test coverage

Run the DataSource test suite anytime to confirm the integration still works:

```bash
cd ~/protocl && source .venv/bin/activate
python -m pytest tests/test_data_sources.py -v
```

43 tests cover: ABC contract, registry behavior, configuration detection, live
gating, happy-path merge of sleep+readiness, sleep-only fallback when
readiness errors, every error code path (401/403/429/5xx/transport/JSON), and
the seconds→hours conversion edge cases.
