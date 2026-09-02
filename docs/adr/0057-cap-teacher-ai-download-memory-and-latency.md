# Cap Teacher AI download, memory, and latency

Each Teacher AI tier must keep its selected wire bundle at or below 1.5 GB and measured peak browser or device memory at or below 4.0 GB. Primary warm time-to-first-token p95 is five seconds with at least two tokens per second in 95 percent of runs; fallback time-to-first-token p95 is 15 seconds and its 128-token draft p95 is 120 seconds; cancellation is two seconds for both. A 60-minute, 100-request physical-device soak must show no crash, OOM, OS kill, UI freeze, or retained-memory growth above ten percent.
