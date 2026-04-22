## 2024-04-22 - [O(N) List Deduplication]
**Learning:** Found O(N^2) list membership checks (`if item not in lst: lst.append(item)`) used for deduplicating nested config values (mode names) during every `tools/list` request, which could block the main event loop if the config scales.
**Action:** Always use order-preserving O(N) deduplication via `list(dict.fromkeys(generator))` in high-frequency path endpoints like `tools/list` to ensure predictable performance.
