## 2024-05-02 - [Asynchronous Config Pre-loading]
**Learning:** In a heavily asyncio-driven application, seemingly fast synchronous operations like `json.load` for configuration files can create hidden micro-stalls on the main event loop. If lazy-loaded on the first incoming request, this file I/O blocks the entire server from processing concurrent requests until the disk read completes. This is especially impactful in high-concurrency environments like MCP servers.
**Action:** Always proactively pre-load required configurations or heavy resources during server startup events (e.g., `@app.on_event("startup")`) by offloading them to worker threads via `asyncio.to_thread()`. This guarantees immediate cache hits and prevents blocking the event loop when the first burst of user requests arrives.

## 2024-05-05 - [Asynchronous Browser Profile I/O]
**Learning:** File system operations like `shutil.copytree` and `shutil.rmtree` used for copying and deleting Playwright profiles are synchronous and can take significant time. When executed directly on the main event loop in an asyncio-driven application, they create hidden micro-stalls, blocking the server from processing concurrent requests and degrading performance during high concurrency.
**Action:** Always offload blocking file I/O operations, such as profile copying and cleanup, to worker threads using `await asyncio.to_thread()`. This prevents stalling the main event loop and maintains responsiveness.

## 2024-05-15 - [Playwright N+1 Browser Round-Trips]
**Learning:** When retrieving text or evaluating conditions on multiple elements found by a Playwright locator, looping over the items and calling `await items.nth(i).inner_text()` creates an N+1 query problem. Each loop iteration triggers a separate blocking network round-trip to the browser, causing significant overhead and slowing down the operation, especially when scanning a list or menu.
**Action:** Always fetch data for all matched elements in a single network call using methods like `await items.all_inner_texts()` or by executing a bulk script via `page.evaluate()`, then process the resulting array locally in Python.
