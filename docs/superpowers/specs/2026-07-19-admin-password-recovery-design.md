# PathLab Viewer Admin Password Recovery Design

## Objective

Give the single PathLab Viewer administrator two secure password-management paths:

1. Change the password while authenticated.
2. Recover a forgotten password with a short-lived, server-issued one-time code.

The feature must preserve the current one-admin model, Argon2id password storage, login-required administration, zero-cost OCI deployment, and anonymous published-slide viewing. It must not add email, SMS, external identity providers, or a permanent browser-usable recovery secret.

## User Experience

### Change password

The authenticated admin page adds an **Account security** action. It opens a compact form containing:

- current password;
- new password;
- new-password confirmation.

The browser validates matching confirmation, but the API remains authoritative. On success, the API revokes every session and active recovery code, including the current session. The response expires the current session cookie. The browser clears its CSRF token, returns to the sign-in screen, and shows: `Password changed. Sign in again.`

### Forgot password

The sign-in panel adds **Forgot password?**. It opens a recovery form containing:

- username, defaulting to `admin`;
- one-time recovery code;
- new password;
- new-password confirmation.

The page explains that the server owner must generate a recovery code. It displays the production command without exposing filesystem paths, secrets, or database details:

```sh
docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin
```

The recovery code is entered only over the existing HTTPS site. On success, the browser returns to sign-in and shows: `Password reset. Sign in with your new password.` Invalid, used, superseded, or expired codes all produce the same message: `Invalid or expired recovery code.`

## Password Rules

- Password length is 12 to 128 Unicode characters.
- The new password must differ from the current password when changing it while signed in.
- The server never logs or returns passwords.
- Passwords continue to use the existing Argon2id hashing configuration.
- Confirmation is frontend-only; the API receives and hashes only the validated new password.

## Recovery-Code Lifecycle

The CLI command `pathlab-admin issue-recovery-code --username admin` performs the only code-issuance operation. There is no public or authenticated HTTP endpoint that can issue a code.

Issuance behavior:

- Verify the requested administrator exists.
- Generate at least 256 bits of randomness with Python's `secrets` module.
- Display the URL-safe code exactly once on standard output.
- Store only a SHA-256 digest of the code.
- Set expiry to 15 minutes after issuance.
- Invalidate every earlier unused recovery code for that user.
- Record an `auth.recovery_code_issued` audit event without recording the code or its digest.

Consumption behavior:

- Look up the user and active code inside one database transaction.
- Compare the submitted code digest in constant time.
- Reject expired, consumed, or superseded codes using the generic public error.
- Hash and save the new password.
- Atomically mark the code consumed with a conditional update that succeeds only while the code is active and unexpired; require exactly one updated row.
- Invalidate all other recovery codes for the user.
- Delete every session belonging to the user.
- Expire the session cookie in the response if the recovering browser has one.
- Record an `auth.password_recovered` audit event without sensitive values.

A code is single-use even when the client retries after a successful response. Concurrent attempts are serialized by the SQLite write transaction; only one can commit as successful.

## Data Model and Migration

Add a `password_recovery_codes` table:

| Column | Purpose |
| --- | --- |
| `id` | Generated opaque identifier |
| `user_id` | Foreign key to `users.id`, indexed |
| `code_hash` | Unique SHA-256 hexadecimal digest |
| `expires_at` | UTC expiry timestamp, indexed |
| `consumed_at` | UTC timestamp when successfully used; nullable |
| `invalidated_at` | UTC timestamp when superseded or administratively invalidated; nullable |
| `created_at` | UTC creation timestamp |

Add a `password_recovery_attempts` table for cross-worker throttling:

| Column | Purpose |
| --- | --- |
| `id` | Generated opaque identifier |
| `client_key_hash` | SHA-256 digest of normalized username plus client address |
| `attempted_at` | UTC timestamp, indexed |

Attempts older than 24 hours are deleted opportunistically during issuance and recovery. An Alembic migration creates and removes both tables. Production startup already runs `alembic upgrade head`, so deployment applies the schema before the API accepts traffic.

## API Contract

### Authenticated password change

`POST /api/v1/auth/password`

Requirements:

- valid session cookie;
- valid `X-CSRF-Token` header;
- JSON body: `currentPassword`, `newPassword`.

Responses:

- `204`: password changed and all sessions revoked;
- `400 PASSWORD_REUSE`: new password matches current password;
- `400 CURRENT_PASSWORD_INVALID`: current password is missing or incorrect;
- `400 INVALID_PASSWORD`: new password violates policy;
- `401`: session is absent or expired;
- `403`: CSRF validation failed;
- `429`: throttled.

The wrong-current-password response must not include the submitted password or password hash. A successful change also invalidates every outstanding recovery code for that user.

### Forgotten-password recovery

`POST /api/v1/auth/password/recover`

Requirements:

- JSON body: `username`, `recoveryCode`, `newPassword`;
- no session or CSRF token, because recovery starts unauthenticated;
- HTTPS at the public edge.

Responses:

- `204`: password reset, recovery codes invalidated, and all sessions revoked;
- `400 INVALID_PASSWORD`: new password violates policy;
- `400 INVALID_RECOVERY_CODE`: username/code pair is invalid, expired, consumed, or superseded;
- `429`: throttled.

Unknown usernames and invalid codes share the same status, error code, and message.

## Abuse Protection

- Password change attempts use the authenticated user ID and client IP as their throttle key.
- Recovery attempts use client IP plus a normalized username digest; normalization trims surrounding whitespace and applies Unicode case-folding, and the raw username is not retained in throttle state.
- Five failed attempts within five minutes block further attempts for five minutes.
- Successful recovery deletes attempt rows for that recovery throttle key.
- Issuing another recovery code invalidates earlier codes, allowing the owner to recover from accidental disclosure.
- Recovery codes never appear in HTTP responses, application logs, audit details, or browser storage.
- The CLI output warns that the code expires in 15 minutes and should be copied only into the HTTPS recovery form.

The current in-memory throttle remains sufficient for login and authenticated password changes. With two API workers, its enforcement is per process, so the effective ceiling may be higher than five attempts. The recovery endpoint therefore records failed attempts in `password_recovery_attempts` and enforces the five-attempt window transactionally. This closes the multi-worker gap for the security-sensitive recovery path without introducing Redis or another paid service.

## Frontend State

The admin page has three unauthenticated modes:

- sign in;
- forgot-password instructions and reset form;
- reset-success confirmation returning to sign in.

It has an authenticated account-security dialog for password change. Password inputs use appropriate autocomplete values:

- `current-password` for the current password;
- `new-password` for new and confirmation fields;
- `one-time-code` for the recovery code.

Submission controls remain disabled while a request is active. Password values are cleared after success, cancellation, or failure. Recovery codes are never written to `localStorage` or `sessionStorage`.

## Audit Events

Add these actions:

- `auth.password_changed` with the administrator as actor;
- `auth.recovery_code_issued` with the administrator as target and no browser actor;
- `auth.password_recovered` with the administrator as target and no authenticated actor;
- `auth.password_recovery_failed` containing only a normalized reason category, never username, password, code, or digest.

The existing `pathlab-admin reset-password` emergency command adopts the same revocation behavior: after changing the password it deletes all sessions, invalidates active recovery codes, and records `auth.password_reset_by_cli`. This prevents a server-side reset from leaving an old browser session authenticated.

## Test Strategy

Backend tests must prove:

- authenticated password change requires the correct current password and CSRF token;
- password policy and password-reuse checks are stable;
- changing a password revokes all existing sessions;
- old credentials fail and new credentials succeed;
- changing a password or using the emergency CLI reset invalidates outstanding recovery codes;
- CLI issuance stores only a digest and invalidates an earlier code;
- a valid code resets the password exactly once;
- expired, consumed, superseded, malformed, and unknown-user cases are indistinguishable;
- recovery revokes all sessions and recovery codes;
- five failed attempts trigger throttling across separate app instances sharing SQLite;
- audit rows contain no submitted secrets;
- the Alembic upgrade produces the new table.

Frontend tests must prove:

- the forgot-password mode is reachable from sign-in and can return safely;
- recovery and change forms validate confirmation;
- successful password change clears CSRF state and returns to sign-in;
- successful recovery returns to sign-in;
- password and recovery-code inputs are cleared and never persisted.

Deployment verification must prove on the OCI site:

1. `/livez` and `/readyz` remain healthy after migration.
2. The CLI issues a code without printing it into deployment logs.
3. The HTTPS recovery flow accepts that code once.
4. The old password and old sessions fail.
5. The new password signs in.
6. Slide upload, administration, and a published viewer link still work.

The live recovery code used for verification is treated as a secret and is not copied into commits, test evidence, shell history, or the final report. Deployment does not change the production administrator password until the owner explicitly approves that credential rotation. Without that approval, the complete reset is proven in an isolated production-equivalent Compose environment while production verification stops after migration health and safe code issuance.

## Scope Boundaries

Included:

- one-admin password change;
- server-issued one-time recovery codes;
- browser recovery form;
- session revocation, throttling, auditing, tests, and OCI deployment.

Excluded:

- email or SMS delivery;
- multiple administrators;
- self-registration;
- external identity providers;
- password hints or security questions;
- permanent recovery keys;
- changing the anonymous public-slide access model.
