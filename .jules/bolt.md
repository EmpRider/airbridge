## 2024-05-18 - [Offload blocking file I/O to thread in asyncio]
**Learning:** `shutil.copytree`, `shutil.rmtree`, and `json.load` are blocking file I/O operations. When run in the main thread of an asyncio event loop (especially inside Playwright applications), they stall the entire server loop resulting in latency spikes and blocked concurrency.
**Action:** Always wrap blocking file I/O operations (like `shutil.rmtree`, `shutil.copytree`, `json.load`) in `asyncio.to_thread(...)` when operating within an `asyncio` architecture to preserve loop performance.

## 2024-05-18 - [O(N) vs O(N^2) deduplication]
**Learning:** Loop-based unique item collection checking list membership via `if item not in list: list.append(item)` is O(N^2) time complexity. Using `list(dict.fromkeys(list))` preserves insertion order but guarantees O(N) deduplication time.
**Action:** Always use `list(dict.fromkeys(items))` to deduplicate lists while preserving order, to optimize from O(N^2) to O(N).
