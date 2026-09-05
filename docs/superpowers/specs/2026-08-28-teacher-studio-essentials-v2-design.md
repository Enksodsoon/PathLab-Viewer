# Teacher Studio Assessment Contract v2 — Design

Status: approved for implementation on `codex/assessment-08-teacher-studio-essentials-v2`.
Production activation remains explicitly out of scope and `PATHLAB_ASSESSMENT_ENABLED`
remains false by default.

## Goals and non-goals

V2 makes assessment sections, presentation, routing, validation, feedback, lightweight
slide media, and education metadata first-class while preserving every published v1
contract. The canonical teacher workflow is Description → Questions → Responses →
Settings. The canonical results product is Responses; the old report route redirects.

This change does not introduce a general image service, new worker, new dependency,
deployment, production activation, protected capacity campaign, or certification claim.
Slide thumbnails are the only question media and remain in the direct assessment asset
tree. Admin URLs, filesystem paths, WSI proxy URLs, answer keys, scoring rules, feedback,
and annotation geometry are excluded from learner payloads unless an explicit release
policy permits a sanitized representation.

## Version boundary

`AssessmentDocument` is a discriminated v1/v2 union. A missing `schema` is accepted as
legacy v1 only. It is never upgraded by inference. New drafts use
`pathlab.assessment/2`. The existing v1 compiler and publish behavior stay unchanged.

V1 migration is explicit and revision checked. It clones the source into a new v2 draft,
leaves the source untouched as a backup, creates one deterministic section, and retains
item IDs, points, option keys, feedback, and slide references.

## V2 document model

A v2 document contains bounded title and description, ordered sections, presentation
settings, and release defaults. Each section owns a stable ID, title, optional description,
optional slide context, and ordered items. Supported item types are multiple choice,
checkboxes, dropdown, rating, short answer, paragraph, diagnostic field, and
section/information. Response items may define validation, help text, authored correct and
incorrect feedback, one slide-thumbnail media reference, education metadata, and routing.

Choice options have stable IDs and labels. Keys and routes refer to IDs, never labels.
Rating uses min 1 and max 3 through 10 inclusive with numbers, stars, hearts, or thumbs-up.
Authored and manual feedback use separate release flags.

Limits are fail-closed: 4 MiB encoded document, 75 sections, 100 items, 10 options per
item, 50 distinct slides, title 200, description 2,000, help text 1,000, general messages
1,000, validation messages 500, manual feedback 4,000, teacher notes 2,000, and one media
reference per item.

## Ordering and branching

Deterministic option/item ordering sorts SHA-256 digests of `seed:itemId`, with stable ID
tie-breaking. Sections never shuffle. Response questions shuffle only in contiguous runs;
information blocks are hard boundaries. Stored attempt seeds survive reconnect and
takeover. Practice preview seeds are browser-local, and Reset changes the preview seed.

Branching evaluates on section exit. Routes target complete sections. Recalculation removes
newly unreachable responses from React state and the IndexedDB outbox. Unreachable required
items do not block review. The backend independently computes reachability and ignores
unreachable answers for validation and scoring.

## Persistence and APIs

Migration `20260828_0035` adds `manual_feedback` JSON and nullable
`graded_by_user_id` to immutable assessment score versions. Existing `created_at` is the
grading timestamp. Administration `settings` stores collection and release configuration;
existing `closes_at` remains the scheduled-close source of truth.

New or extended interfaces:

- `POST /drafts/{id}/migrate-v2`: revision-checked v1 clone.
- `POST /drafts/{id}/preflight`: shared authoritative validation used by publish.
- `POST /drafts/{id}/publish`: v1 compatible; v2 supports atomic multi-class publication.
- `PATCH /administrations/{id}/collection`: acceptance, close, limit, and closed message.
- `GET /administrations/{id}/monitor`: count-only operational state.
- `POST /administrations/{id}/manual-grades`: atomic individual/grouped immutable grades.
- Existing result/release endpoints return policy-built learner review fields.
- Existing imports mint fresh section/item/option IDs and safely remap or remove routes.

One immutable assessment version is created for a multi-class publish. Administrations are
created atomically. The immediate response may include one-time raw access codes and all
class links; raw codes are never persisted or returned again. Legacy single-v1 top-level
fields remain.

## Teacher and learner surfaces

The flat builder becomes section cards with add, duplicate, delete/undo, collapse, pointer
and keyboard reorder, accurate numbering, searchable filtered navigation, issues,
readiness, drag state, and assignment preview. Expand/collapse use icon buttons. Required
badges are red. The editor supports stable option CRUD/reorder/paste, Other, dropdown,
rating styles, validation, feedback, media, metadata, routing, blueprint warnings,
templates, local paste-to-create, assessment library import, and lazy QR download.

Preview, practice, formative, and quiz share a learner renderer at 1,200, 768, and 390 px
preview widths. A section maintains one OpenSeadragon viewer; item overrides replace tile
sources without recreating it. Navigation lock disables viewer gestures without trapping
keyboard focus.

Responses owns Summary, Questions, Individuals, and Needs grading. It supports selectors,
search, filters, previous/next, partial points, feedback, normalized grouped short-answer
grading, save-and-next, progress, and conflict reload while retaining unsaved comments
locally. Count-only monitor polling occurs every 15 seconds only while Responses is visible
and the document is visible.

## Privacy and release matrix

Learner review is constructed field by field. Before permitted release, serialized payloads
exclude answer keys, accepted answers, diagnoses, regions, scoring, authored feedback,
manual feedback, annotation geometry, admin URLs, and filesystem paths. Release policy has
independent booleans for score, answers, authored feedback, manual feedback, and sanitized
annotation overlays. Immediate release is downgraded to manual with a warning whenever any
reachable item requires manual grading.

## Verification and evidence boundary

Matching TypeScript/Python fixtures prove deterministic ordering and routing. Contract,
validator, migration, publish, scoring, reachability, privacy, closure, ownership,
analytics, export, and conflict tests cover backend behavior. Frontend and Playwright tests
cover authoring micro-features, learner reconnect/outbox behavior, grading/release, review,
accessibility, and mobile Slide/Answer behavior. A bundle check rejects teacher-only chunks
from the learner graph and targets at most 15 kB gzip growth.

Completion is reported as `BUILT`, production disabled, capacity `NOT_EVALUABLE`. Local,
CI, migration, browser, deployment, activation, capacity, and certification evidence remain
separate claims.
