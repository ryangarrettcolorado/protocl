# v3.2 — Beta Tier (Google SSO multi-user)

Protocōl moves from a single-tenant personal app to a private, invite-only
beta with strict per-user data isolation, owner impersonation under consent,
and a full security audit trail.

## Authentication

- Uses Streamlit's **native OIDC** integration (`st.login()`, `st.user`,
  `st.logout()`), which requires `streamlit >= 1.42` and `authlib >= 1.3.2`.
- The Google provider is configured under `[auth]` in
  `.streamlit/secrets.toml` (template in `.streamlit/secrets.toml.example`).
  Real secrets are gitignored.
- The auth guard `auth.require_auth()` runs once per page load from the nav
  shell (`modules/shell.py::boot()`), so every existing page is protected
  without per-page edits.

### Flow

1. Not logged in → login screen, `st.stop()`.
2. Logged in but email not on the allowlist → denial screen, `denial`
   audit event, `st.stop()`.
3. Allowed → role + `profile_id` written to `st.session_state`, `login`
   audit event, page renders.

## Allowlist & roles

`config/allowlist.yaml` defines exactly one owner and up to five beta users:

```yaml
owner:
  email: ryangarrettcolorado@gmail.com
  name: Ryan Garrett
beta_users:
  - email: placeholder1@example.com
  # ... up to 5
```

`auth.resolve_principal(email, allowlist)` is pure (no Streamlit) and unit
tested. Matching is case- and whitespace-insensitive; the owner wins over a
duplicate beta entry. Beta `profile_id` is the slugified email
(`friend@gmail.com → friend_at_gmail_com`).

## Data isolation — `ProfileStorage`

- Resolves every read/write to `data/profiles/<profile_id>/`. The owner reuses
  the legacy `data/ryan/` directory so no real data is migrated.
- `profile_id` is read from `st.session_state` in `__init__` and is **never**
  a constructor argument — page code cannot target another user's directory.
- `get_path()` rejects path traversal (`/`, `\`, `.`, `..`).
- App-wide read-only resources and shared logs live under `data/shared/`.
- New beta profiles are seeded with empty CSV templates; users may opt into
  anonymized onboarding data copied from `data/samples/`.

## Owner impersonation (read-only)

- The owner may view a beta user's dashboard **only** if that user opted in
  (`consent.owner_can_view`).
- `start_impersonation()` sets `read_only=True`; `ProfileStorage._guard_write`
  and `data_loader._guard_writable` raise on every write attempt.
- A persistent banner is shown and `impersonation_start` / `impersonation_end`
  are audit-logged.

## Consent, audit, feedback

- **Consent** (`consent.py`) — privacy acceptance + optional owner-visibility.
  Revocation is **timestamped, not deleted**, preserving the audit trail.
- **Audit** (`audit.py`) — append-only `data/shared/audit_log.csv`; IPs stored
  only as one-way SHA-256 hashes.
- **Feedback** (`feedback.py`) — in-app widget writing to a shared log;
  surfaced on the owner-only Feedback admin page.

## Admin pages (owner-only)

`30_admin_beta_overview`, `31_admin_feedback`, `32_admin_audit_log`,
`33_admin_llm_costs` plus `99_privacy`. Each guards with `require_auth()` +
`is_owner()`, and the nav hides `owner_only` pages from beta users.

## Tests

- `test_auth.py` — allowlist matching, slugification, role resolution.
- `test_storage.py` — isolation, traversal rejection, read-only guard.
- `test_consent.py` — consent capture and timestamped revocation.
