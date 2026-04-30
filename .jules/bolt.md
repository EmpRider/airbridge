## 2024-04-30 - O(N^2) Anti-Pattern in Mode Deduplication
**Learning:** Found an O(N^2) anti-pattern in `mcp_manager/server.py` and `mcp_manager/mcp_client.py` where unique `mode` names from configuration are extracted using `if item not in list: list.append(item)`.
**Action:** Always prefer dictionary-based order-preserving deduplication (O(N) lookup) using `dict.fromkeys()` or `list({item: None for item in items}.keys())` instead of list containment checks in loops, especially for config-parsing loops where the number of tasks or modes could grow.
