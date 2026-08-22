# Identity and Governance Foundation

## Status and boundary

This is the first deployable Program 1 identity slice. It is disabled by default with
`PATHLAB_IDENTITY_GOVERNANCE_ENABLED=false`. It does not activate OIDC, create public
learner routes, or change temporary live-Classroom participant credentials.

The implementation is an additive foundation, not a production identity claim. It may
reach `BUILT` after merge and protected checks; tenant conformance, pilot validation,
production certification, and clinical qualification remain out of scope.

## Fixed staff roles

The server owns the role-to-capability mapping. Clients never supply capabilities.

| Role | Capabilities |
|---|---|
| Owner | identity, Library, Classroom, Education, Research, audit |
| Admin | identity, Library, Classroom, Education, audit |
| Instructor | Classroom, Education, learner read |
| Teaching Assistant | Classroom, learner read |
| Researcher | Research, learner read |
| Auditor | audit read |

Memberships are organization-scoped and may be disabled. An organization must retain
at least one active Owner. The existing administrator is backfilled as Owner of the
deterministic default organization. `pathlab-admin create-admin` creates the same
default ownership records on a fresh database.

## Data separation

- Staff identity continues to use the existing `users` and `sessions` records.
- Learners use pseudonymous `learner_profiles` and hashed `learner_credentials`.
- Teaching pseudonyms and research pseudonyms are separate records.
- Cohort enrollment is organization-scoped.
- Dormant OIDC links store an issuer and a one-way subject hash; OIDC is not active.
- Temporary Classroom participants remain in `classroom_participants`; no join request
  performs an organization, membership, OIDC, cohort, or learner-profile lookup.
- Identity responses never serialize password hashes, access-token hashes, recovery
  hashes, invitation hashes, or learner records.

Every new organization-owned record carries `organization_id`, `schema_version`, actor
or creator linkage, timestamps, and audit linkage where applicable. Tokens and recovery
credentials are stored only as SHA-256 digests. Raw credentials will be returned only
at a future explicit issuance boundary and never logged.

## Gated API

The initial namespace is `/api/v2/admin/identity`:

- `GET /context` lists only the authenticated staff member's active memberships.
- `POST /organizations` creates an organization and an Owner membership.
- `POST /organizations/{id}/memberships` assigns a fixed role to an existing staff user.
- `DELETE /organizations/{id}/memberships/{membershipId}` disables a membership and
  fails closed when it would remove the last active Owner.

Mutations require the existing CSRF protection. `X-PathLab-Organization` selects an
active organization only when the authenticated staff member has an active membership.
Cross-organization identifiers return a fail-closed authorization response.

## Threat and privacy analysis

| Risk | Control |
|---|---|
| Cross-organization access | Every context and mutation resolves an active membership server-side. |
| Client-invented authority | Capabilities are a fixed server mapping from constrained roles. |
| Last-owner lockout | Disabling the final active Owner returns a conflict. |
| Credential disclosure | Only hashes are durable; API serialization excludes credential fields. |
| Learner identity leakage | Learner records have no public endpoint in this slice. |
| Classroom latency regression | Identity routes register only on the general API and are absent from SSE/join paths. |
| Unsafe activation | Flag defaults false in settings, both environment examples, and Compose. |
| Migration loss | Migration is additive, backfills deterministically, and has a tested downgrade. |

## Remaining Program 1 work

Subsequent narrow PRs will add invitation redemption and expiry, learner credential
issuance/recovery/revocation, cohort workflows, capability guards for each existing
administrator domain, security-event export, and the simple active-organization UI.
Those capabilities must not be inferred from this foundation.
