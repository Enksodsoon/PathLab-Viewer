# Classroom polling verification

Labels: wayfinder:ticket

## Confirmed verification defects

Fresh main ed1aa6a CI37167261430 failed only the web job: the transient polling test dispatched visibilitychange before the polling effect installed its listener. A corrected 100-case diagnostic reproduced two missing-listener witnesses after the review heading appeared. The old timer test also passed with the inFlight guard removed because fake timers started after the real polling interval was created. These are verification fixture defects, not an additional proved production defect.

## Repair

Flush initial rendering and passive effects through async act, assert the resulting review heading, and install fake timers before mounting for the timer/visibility collision. Supply a valid subsequent phase response so a removed concurrency guard fails on two requests versus one, rather than an unrelated undefined response. Keep transient retention, terminal denial and stale-invitation assertions. Application source remains unchanged.

## Evidence and next checks

Original focused suite passed despite repeated race; original missing-guard mutation passed. Repaired focused suite passed three cases. Repaired missing-guard mutation fails explicitly with two API calls instead of one; the guard was restored byte for byte. Logs are retained under var/classroom-timer-original-mutation.log, var/classroom-timer-fixed-mutation.log and var/classroom-polling-fixed-focused.log. Corrected readiness replay passed 102 cases (100 diagnostic repetitions plus two existing cases). Frontend lint passed and independent fixture review is clear. Full frontend verification and immutable browser receipt/inventory refresh are pending. The receipt covers test sources: retain that boundary and capture the new immutable input set. No source license admission changes are authorized by these engineering checks.

Original 954 source entries and 29 aggregate claims remain unchanged; track this verification defect separately from the 44 application campaign findings. Production remains verified c37cf81; no new deployment is claimed.
