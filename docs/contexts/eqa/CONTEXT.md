# EQA

This context owns external-quality schemes, accountable Institution participation, sealed responses, versioned scoring, adjudication, and reports.

## Language

**Scheme**:
An enduring external-quality program defining its purpose, participation rules, governance, and reporting policy.
_Avoid_: Course, assessment program

**Round**:
A scheduled Scheme event with immutable cases, deadlines, participants, and scoring policy.
_Avoid_: Exam Session, distribution

**Case Version**:
An immutable EQA case containing its governed assets, prompt, expected evidence, and interpretation policy.
_Avoid_: Question, slide

**EQA Participant**:
A participating Institution or laboratory represented by a purpose-specific Institution identity.
_Avoid_: Learner, user, account

**EQA Submitter**:
The one currently authorized staff member who irreversibly seals an EQA Participant's collaborative draft as its Sealed Submission.
_Avoid_: Author, approver, last editor

**Sealed Submission**:
The immutable response package accepted for one EQA Participant in one Round.
_Avoid_: Attempt, answer, draft

**Scoring Version**:
An immutable scoring and adjudication definition applied to Sealed Submissions.
_Avoid_: Rubric edit, grade rule

**Appeal**:
A governed request to review a score or adjudication without altering the original Sealed Submission or Scoring Version.
_Avoid_: Regrade, correction

**EQA Report**:
The immutable participant or aggregate result issued under a named Scoring Version and review state.
_Avoid_: Grade, dashboard

**Suppressed Aggregate**:
An aggregate EQA result withheld because its contributing participant count is fewer than ten.
_Avoid_: Empty report, hidden score, small cohort warning

**EQA Launch Gate**:
The exact-host production campaign for one 100-case Round, 300 EQA Participants, two collaborating staff per Institution, deadline sealing, scoring, reporting, appeal, disconnect, restart, and isolation evidence.
_Avoid_: Assessment capacity, Classroom capacity

## Retention ceilings

- Collaborative drafts expire no later than 90 days after Round closure.
- Distribution and access logs expire no later than one year after Round closure.
- Sealed Submissions, Scoring Versions, Appeals, and issued EQA Reports expire no later than seven years after Round closure.
- Deidentified aggregate trend records expire no later than ten years after Round closure.
