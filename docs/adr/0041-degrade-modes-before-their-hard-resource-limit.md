# Degrade modes before their hard resource limit

An active mode enters THROTTLED at 80 percent of its memory or CPU envelope, pausing background work; at 90 percent it enters SHEDDING, rejects new heavy admissions, and removes optional media or rebuildable work. Reaching a hard cgroup limit triggers a Safety Shutdown of only the offending Mode Processes while the Resident Control Plane remains available; disk swap, kernel-selected cross-service termination, and automatic restart loops are prohibited, and checkpointed or provisional state must reconcile before an audited retry.
