# Administrator Password Recovery

## Purpose

PathLab Viewer supports one administrator account. Password management has two paths:

1. an authenticated password change;
2. recovery with a short-lived, server-issued one-time code.

The design avoids email, SMS, external identity providers, permanent browser recovery secrets, and additional infrastructure such as Redis.

## Security properties

- Passwords contain 12–128 Unicode code points and are stored with Argon2id.
- Recovery codes contain at least 256 bits of randomness.
- A code expires 15 minutes after issuance and can be used only once.
- Only a SHA-256 digest of the code is stored.
- Issuing a new code invalidates all earlier unused codes for that account.
- Password change, password recovery, and the emergency CLI reset revoke all active sessions and outstanding recovery codes.
- Unknown usernames and invalid, expired, consumed, malformed, or superseded codes produce the same public error.
- Passwords, recovery codes, and code digests must never enter logs, audit details, browser storage, screenshots, commits, or tickets.

## Recovery-code issuance

A code can be issued only from the server command line:

```sh
docker compose -f deploy/compose.yaml exec api \
  pathlab-admin issue-recovery-code --username admin
```

The command verifies that the administrator exists, creates the code, stores its digest and expiry, invalidates older codes, records a non-sensitive audit event, and writes the plaintext code exactly once to standard output.

There is no HTTP endpoint that issues recovery codes.

## Browser flows

### Authenticated password change

`POST /api/v1/auth/password`

The request requires a valid administrator session and CSRF token. The server verifies the current password, validates the replacement, rejects password reuse, saves the new hash, revokes sessions and recovery codes, and expires the current browser session.

### Forgotten-password recovery

`POST /api/v1/auth/password/recover`

The request contains the username, one-time recovery code, and new password. It starts without a session or CSRF token and must be used only through the HTTPS site. A successful recovery consumes the code atomically, changes the password, revokes all sessions and remaining codes, and clears any session cookie held by the browser.

## Persistence

| Table | Purpose |
|---|---|
| `password_recovery_codes` | Code digest, owner, expiry, consumption, invalidation, and creation timestamps |
| `password_recovery_attempts` | Hashed client/username throttle key and attempt timestamp |

Recovery attempts are enforced through SQLite so the limit remains effective across multiple API workers. Five failed attempts within five minutes produce a five-minute block. Old attempt records are removed opportunistically.

## Audit events

The system records lifecycle events without sensitive values:

- `auth.password_changed`;
- `auth.recovery_code_issued`;
- `auth.password_recovered`;
- `auth.password_recovery_failed`;
- `auth.password_reset_by_cli`.

## Verification requirements

Automated tests cover password policy, CSRF protection, current-password validation, session revocation, one-time code use, indistinguishable invalid-code cases, persistent throttling, migration behavior, audit redaction, frontend secret clearing, and request contracts.

Deployment verification must confirm migration health, safe code issuance, one-time HTTPS recovery, invalidation of old credentials and sessions, successful sign-in with the replacement password, and continued slide administration. Operational instructions are maintained in `deploy/README.md`.
