# Keep observability local, bounded, and actionable

Zero-Cash observability will use structured journald Operational Logs, OpenMetrics scraped every 30 seconds, raw metrics retained for seven days and five-minute aggregates for 13 months, and error-triggered or at-most-one-percent Diagnostic Traces retained for 24 hours. `pathlab-control` serves the local operator dashboard and durable Operator Alerts, optional Institution SMTP may copy an alert, and production emits no mandatory external telemetry, analytics, hosted logging, tracing, or dashboard traffic.
