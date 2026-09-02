# Assessment

This context owns versioned assessment material, timed learner work, confirmation of submissions, and educator-controlled grading.

## Language

**Item Version**:
An immutable publication of one assessment question, stimulus, response contract, and scoring definition.
_Avoid_: Question, live item

**Item Type**:
The response contract of an Item Version: single choice, multiple choice, true/false, numeric, short text, essay, hotspot, shared stimulus, or native WSI point or region.
_Avoid_: Question format, widget, answer control

**Exam Session**:
A scheduled assessment event bound to immutable item, accommodation, content, and roster snapshots.
_Avoid_: Test, assessment course

**Attempt**:
One learner's governed opportunity to complete an Exam Session.
_Avoid_: Submission, exam record

**Attempt Lease**:
A server-issued authorization renewed every five minutes and valid for at most 30 minutes, binding one learner, device, Attempt, immutable Exam Session versions, and server deadline.
_Avoid_: Exam token, offline permission

**Attempt Device Transfer**:
An audited staff authorization that moves one active Attempt binding to a replacement device without creating a second Attempt.
_Avoid_: Second login, new attempt, device reset

**Response Revision**:
A monotonically ordered saved state of one response within an Attempt.
_Avoid_: Autosave, answer event

**Provisional Journal**:
Encrypted local evidence of disconnected work that has not been accepted as authoritative by PathLab.
_Avoid_: Offline submission, local save

**Sealed Journal**:
A read-only Provisional Journal closed at the earlier of server deadline or Attempt Lease expiry and awaiting bounded server validation.
_Avoid_: Offline submission, completed exam

**Submission Receipt**:
The immutable confirmation that PathLab durably accepted an Attempt for grading.
_Avoid_: Submitted screen, local confirmation

**Scoring Version**:
The immutable deterministic scoring and manual-evaluation definition applied to accepted responses for one Exam Session.
_Avoid_: Grading settings, live rubric, AI score

**Grade**:
An educator-authorized evaluation tied to a Submission Receipt and scoring version.
_Avoid_: AI score, result estimate

**Assessment Appeal**:
A governed request lodged within 30 days of result issuance to review a Grade without mutating its original Submission Receipt or scoring evidence.
_Avoid_: Regrade, correction, complaint

**High-Stakes Moderation**:
An independent review required before a high-stakes outcome is finalized, with Dual Authorization required for a grade change or credential-bearing outcome.
_Avoid_: Second marking checkbox, teacher approval

**Assessment Launch Gate**:
The exact-host production campaign for 300 simultaneous learners completing a 100-item, 120-minute Exam Session under revision, disconnect, restart, and submission-burst load.
_Avoid_: Assessment capacity, load test

## Retention ceilings

- A Provisional Journal expires no later than seven days after confirmation or invalidation.
- An abandoned draft expires no later than 30 days after its deadline.
- Response Revisions and scoring evidence expire no later than two years after finalization.
- Submission Receipts, final Grades, and grade-change history expire no later than seven years after the associated course closes.
