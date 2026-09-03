# Bound each Research Job to one CPU and four GB

Zero-Cash Research permits exactly one active Research Job with a hard Research Quota of one OCPU, four GB memory, 20 GB ephemeral workspace, four wall-clock hours, and 15 idle minutes before checkpoint and suspension. Dataset Snapshots mount read-only, the runner has no production database credentials, network egress is deny-by-default and requires a separate purpose-bound grant, and only signed Research Artifacts plus provenance may cross back into Research Control.
