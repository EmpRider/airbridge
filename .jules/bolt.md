
## 2024-05-01 - [O(N^2) list membership checks anti-pattern]
**Learning:** Checking list membership inside a loop (`if item not in my_list: my_list.append(item)`) results in O(N^2) performance for N items. In the MCP manager, collecting unique `mode` names for tools dynamically created an accidental O(N^2) loop where list scaling would significantly slow down tool lists retrieval over time.
**Action:** Use dict keys for O(N) order-preserving deduplication instead (e.g. `list(dict.fromkeys(items))`). Applied this fix to both `mcp_manager/server.py` and `mcp_manager/mcp_client.py` for dynamic tool loading endpoints.
