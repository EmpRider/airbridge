## 2025-02-12 - Order-Preserving Deduplication in Python
**Learning:** Found O(N^2) list membership checks (`if item not in list: list.append(item)`) used for collecting unique modes in `mcp_manager/server.py` and `mcp_manager/mcp_client.py`. In Python 3.7+, `dict.fromkeys()` is guaranteed to preserve insertion order, making `list(dict.fromkeys(items))` an O(N) drop-in replacement that maintains correct ordering without sacrificing readability.
**Action:** Always replace O(N^2) list membership checks with `dict.fromkeys()` for order-preserving deduplication in Python.
