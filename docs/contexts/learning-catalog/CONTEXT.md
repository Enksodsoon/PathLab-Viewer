# Learning Catalog

This context owns PathLab's canonical learning structure, learning-group participation, immutable event snapshots, approved achievement definitions, and deterministic learner progress and completion evidence.

## Language

**Course**:
The enduring learning offering under which modules, lessons, cohorts, and activities are organized.
_Avoid_: Class, study pack, assessment course

**Course Version**:
An immutable publication of a Course's ordered structure and referenced content.
_Avoid_: Course copy, live draft

**Module**:
An ordered instructional subdivision of a Course.
_Avoid_: Folder, unit collection

**Lesson**:
A versioned instructional activity or content unit within a Module.
_Avoid_: Page, slide set

**Cohort**:
A named group of learners associated with a Course for a defined teaching period.
_Avoid_: Class, roster, team

**Enrollment**:
The relationship granting one learner participation in one Cohort.
_Avoid_: Membership, roster row

**Roster Snapshot**:
An immutable capture of eligible participants taken for a scheduled Class Session, Exam Session, or EQA Round.
_Avoid_: Live roster, enrollment list

**Learner Progress Evidence**:
A versioned deterministic record of one learner Purpose Identity's completed activities against one exact Enrollment and Course Version.
_Avoid_: Study progress, activity stream, percentage complete

**Completion Evidence**:
An immutable determination that accepted Learner Progress Evidence satisfied the named completion rule for one exact Course Version.
_Avoid_: Course complete flag, Grade, credential

**Achievement Definition**:
The enduring Institution-approved learning achievement for which evidence may be evaluated and an Achievement Credential may later be requested.
_Avoid_: Badge, certificate template, completion event

**Achievement Definition Version**:
An immutable approved publication of an Achievement Definition's eligible Course Versions, deterministic completion rule, permitted Assessment evidence, issuer, validity policy, and minimum evidence requirement.
_Avoid_: Badge version, credential type, mutable criteria

**Achievement Eligibility Proposal**:
An immutable Catalog assertion that named Completion Evidence satisfies one exact Achievement Definition Version, offered to Credential Ledger without authorizing issuance.
_Avoid_: Auto-award, issued badge, completion webhook

**Published Learning Provenance**:
The immutable lineage connecting a published Course Version and its Lessons to their source versions, approvals, and governed references.
_Avoid_: Edit history, author notes, course metadata

## Retention ceilings

- A Course Enrollment expires no later than two years after it ends by completion, withdrawal, cancellation, or Course closure.
- A Roster Snapshot expires no later than two years after its Class Session, Exam Session, or EQA Round closes.
- Learner Progress Evidence and Completion Evidence expire no later than two years after the associated Enrollment ends.
- Published Learning Provenance expires no later than seven years after the associated Course Version, Lesson version, or Achievement Definition Version is archived and has no open governed reference.
- An Achievement Eligibility Proposal expires with its supporting Completion Evidence; admission of a separate Credential Evidence Snapshot does not restart the Catalog clock.
