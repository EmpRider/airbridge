## 2026-04-24 - [Order-Preserving Deduplication in Python]
**Learning:** Checking list membership in a loop `if m["name"] not in all_mode_names: all_mode_names.append(...)` is O(N^2) complexity, which can be an anti-pattern when processing configuration dynamically. In Python 3.7+, `list(dict.fromkeys(...))` achieves order-preserving deduplication with O(N) complexity using dictionary keys.
**Action:** Use dictionary-based structures like sets or dictionaries (e.g., `dict.fromkeys()`) instead of list membership checks for fast and efficient deduplication while maintaining insertion order.
