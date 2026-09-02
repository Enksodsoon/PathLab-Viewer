# Partition the Zero-Cash host with emergency headroom

The declared two-OCPU, 12-GB host will reserve 2 GB for the operating system and page cache, cap the Resident Control Plane at an aggregate 3 GB and 0.75 OCPU, cap all processes in the active Mode Reservation at an aggregate 6 GB and 1 OCPU, and preserve 1 GB plus 0.25 OCPU as untouchable emergency headroom. Cgroup limits enforce the Host Resource Partition, inactive modes consume zero active process resources, and any allocation change invalidates existing capacity evidence until the exact host is requalified.
