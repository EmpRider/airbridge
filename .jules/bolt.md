## 2024-05-02 - [Asynchronous Config Pre-loading]
**Learning:** In a heavily asyncio-driven application, seemingly fast synchronous operations like `json.load` for configuration files can create hidden micro-stalls on the main event loop. If lazy-loaded on the first incoming request, this file I/O blocks the entire server from processing concurrent requests until the disk read completes. This is especially impactful in high-concurrency environments like MCP servers.
**Action:** Always proactively pre-load required configurations or heavy resources during server startup events (e.g., `@app.on_event("startup")`) by offloading them to worker threads via `asyncio.to_thread()`. This guarantees immediate cache hits and prevents blocking the event loop when the first burst of user requests arrives.

## 2024-05-05 - [Asynchronous Browser Profile I/O]
**Learning:** File system operations like `shutil.copytree` and `shutil.rmtree` used for copying and deleting Playwright profiles are synchronous and can take significant time. When executed directly on the main event loop in an asyncio-driven application, they create hidden micro-stalls, blocking the server from processing concurrent requests and degrading performance during high concurrency.
**Action:** Always offload blocking file I/O operations, such as profile copying and cleanup, to worker threads using `await asyncio.to_thread()`. This prevents stalling the main event loop and maintains responsiveness.

## 2024-05-12 - [Playwright N+1 Locator Text Extraction]
**Learning:** Using `await items.nth(i).inner_text()` inside a loop after `await items.count()` creates an N+1 query pattern where each text extraction results in a separate network round-trip between the Node.js test runner and the browser. This can cause significant latency if the list is long.
**Action:** Always use `await items.all_inner_texts()` to fetch all texts in a single batch round-trip, then iterate locally over the result to perform the required logic or to find the index needed for a subsequent click via `await items.nth(i).click()`.

## 2024-07-06 - [Playwright UI State Pre-Verification]
**Learning:** In Playwright UI automation, blindly executing expensive interactions like waiting for and clicking dropdowns before checking if the desired state is already active can add significant unnecessary latency. Also, exact string matching or simple substring matching (`in`) for UI text can be unreliable or cause false positives when models have overlapping names (e.g. 'GPT-4' and 'GPT-4-turbo').
**Action:** Optimize performance by pre-verifying if the target state is active (using `inner_text` with a short timeout inside a `try...except` block) before executing expensive interactions. When checking UI text for generic models, use robust regex matching with negative lookbehinds/lookaheads (`re.search(r'(?<![\w\-])' + re.escape(model_name) + r'(?![\w\-])')`) to prevent false positives and exact-match brittleness.
