# Live Learning

This context owns active teaching sessions, presenter authority, semantically durable interaction, and attendance evidence without treating transient connection state as learning truth.

## Language

**Class Session**:
A scheduled live teaching event bound to immutable content and roster snapshots.
_Avoid_: Classroom, room, live course

**Session Owner**:
The single active authority permitted to order and broadcast one Class Session's state.
_Avoid_: Classroom worker, leader

**Presenter Lease**:
The exclusive, epoch-bound grant permitting an educator to control the shared presentation.
_Avoid_: Teacher lock, host status

**Durable Interaction**:
A committed prompt, question, response, or workspace action whose educational meaning must survive reconnect and recovery.
_Avoid_: Classroom event, activity

**Notebook Submission**:
A learner's explicit selection of device-local notebook content for commitment as a Durable Interaction.
_Avoid_: Notebook sync, autosave, browser backup

**Presence**:
The current best-effort observation that a participant is connected to a Class Session.
_Avoid_: Attendance, participation evidence

**Attendance Interval**:
A durable time interval derived from validated participation evidence rather than a single connection signal.
_Avoid_: Online status, presence record

**Guest Participant**:
A pseudonymous attendee limited to a non-credit Class Session whose activity creates no durable learner evidence.
_Avoid_: Guest learner, temporary enrollment, anonymous student

**Teacher Broadcast**:
A one-publisher, receive-only-student audio/video stream forwarded by an open self-hosted selective forwarding unit using client-side encoding and no server-side transcoding or recording.
_Avoid_: Video conference, webinar service

**Media Fallback**:
The automatic transition from Teacher Broadcast to synchronized slides and text while preserving Class Session continuity and all Durable Interactions.
_Avoid_: Disconnect, failed class

**Live Learning Launch Gate**:
The exact-host 60-minute campaign for one teacher and 1,200 learners performing synchronized DZI viewing, high-rate ephemeral control, durable interaction, reconnect, restart, attendance, and optional qualified media work.
_Avoid_: Classroom capacity, connected clients, SSE capacity

## Retention ceilings

- Presence, pointer, viewport, presenter-control, temporary-pin, and teaching-stroke state is ephemeral and is not written as a historical event stream.
- Connection diagnostics expire no later than 30 days after collection.
- Durable Interactions expire no later than two years after the Class Session closes.
- Attendance Intervals and their minimum supporting evidence expire no later than seven years after the associated course closes.

## Zero-Cash media adapter

- Galene 1.1 is the pinned Teacher Broadcast forwarder for Linux ARM64.
- The teacher receives presenter/operator media permissions; learners receive observe-only permissions through short-lived PathLab-issued tokens.
- VP8 video and Opus audio form the launch codec profile, recording remains disabled, and the sender is capped at the qualified 540p bitrate.
- Galene runs as an unprivileged system service without a database, Redis, or another media control plane.
- Failure of direct UDP or the built-in TURN path invokes Media Fallback; it does not expand the media capacity claim.
