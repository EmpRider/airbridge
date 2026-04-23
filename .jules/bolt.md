## 2024-05-24 - O(N^2) list membership deduplication
**Learning:** Checking for list membership in a loop `if item not in list: list.append(item)` leads to an O(N^2) complexity pattern. In this codebase, gathering mode names dynamically across tasks encountered this performance trap.
**Action:** In Python 3.7+, use dictionary keys for order-preserving deduplication with O(N) complexity (e.g., `list(dict.fromkeys(items))` or a dictionary comprehension).
