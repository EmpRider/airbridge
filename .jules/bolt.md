## 2024-05-02 - [Asynchronous Config Pre-loading]
**Learning:** In a heavily asyncio-driven application, seemingly fast synchronous operations like `json.load` for configuration files can create hidden micro-stalls on the main event loop. If lazy-loaded on the first incoming request, this file I/O blocks the entire server from processing concurrent requests until the disk read completes. This is especially impactful in high-concurrency environments like MCP servers.
**Action:** Always proactively pre-load required configurations or heavy resources during server startup events (e.g., `@app.on_event("startup")`) by offloading them to worker threads via `asyncio.to_thread()`. This guarantees immediate cache hits and prevents blocking the event loop when the first burst of user requests arrives.

## 2024-05-05 - [Asynchronous Browser Profile I/O]
**Learning:** File system operations like `shutil.copytree` and `shutil.rmtree` used for copying and deleting Playwright profiles are synchronous and can take significant time. When executed directly on the main event loop in an asyncio-driven application, they create hidden micro-stalls, blocking the server from processing concurrent requests and degrading performance during high concurrency.
**Action:** Always offload blocking file I/O operations, such as profile copying and cleanup, to worker threads using `await asyncio.to_thread()`. This prevents stalling the main event loop and maintains responsiveness.

## 2024-05-12 - [Playwright N+1 Locator Text Extraction]
**Learning:** Using `await items.nth(i).inner_text()` inside a loop after `await items.count()` creates an N+1 query pattern where each text extraction results in a separate network round-trip between the Node.js test runner and the browser. This can cause significant latency if the list is long.
**Action:** Always use `await items.all_inner_texts()` to fetch all texts in a single batch round-trip, then iterate locally over the result to perform the required logic or to find the index needed for a subsequent click via `await items.nth(i).click()`.

## 2025-02-12 - [Pre-verify UI State to Prevent Redundant Interactions]
**Learning:** In Playwright UI automation, blindly proceeding to click a dropdown menu, wait for visibility, and extract all inner text can cause significant performance stalls if the desired option is already selected. Exact string matching (`==`) or naive substring matching (`in`) on the current state text often fail due to UI variations or substrings (e.g. 'GPT-4' in 'GPT-4-turbo').
**Action:** Always verify if the desired state is already active by inspecting the trigger's `inner_text()` inside a `try...except` block before unconditionally executing expensive interactive operations. Use robust regex matching with negative lookbehinds/lookaheads (e.g., `re.search(r'(?<![\w\-])' + re.escape(model_name) + r'(?![\w\-])', text)`) to accurately confirm the state and avoid false positives.

## 2025-02-13 - [O(N^2) List Remove in Browser Pool Cleanup]
**Learning:** Using `list.remove()` inside a loop over a large array operates in O(N^2) complexity, which can become a bottleneck when cleaning up many idle resources in a high-concurrency pool. Furthermore, Python dataclasses or objects without custom eq/hash methods can throw `TypeError: unhashable type` when attempting to place them directly in a `set` for O(1) lookups.
**Action:** Replace `for item in to_remove: list.remove(item)` patterns with O(N) single-pass filters using slice assignment (`list[:] = [x for x in list if check]`). When filtering custom objects via a set, extract and store a unique identifier (e.g., `context_id`) in the set rather than the object itself to avoid hashing errors.

## 2025-02-14 - [Fast-Path Surrogate Sanitization]
**Learning:** Text sanitization functions that unconditionally use `.encode(errors="surrogatepass").decode(errors="replace")` incur significant performance penalties (up to 3x slower) even on clean text, which is the 99% use case. In applications doing heavy text processing (like simulated human typing character-by-character), this becomes a CPU bottleneck.
**Action:** Always implement a fast-path using `try: text.encode('utf-8')` to validate if text is already clean before falling back to expensive surrogate replacement algorithms.

## 2025-02-23 - [Playwright Batched Locators over Network Loops]
**Learning:** In Python's async Playwright API, `page.locator()` does not throw an exception for malformed CSS selectors at creation time; it only throws during evaluation. Replacing efficient comma-separated strings (`', '.join()`) with a loop that individually evaluates selectors (e.g., `await loc.count()`) to safely chain valid ones with `locator.or_()` introduces a severe N+1 performance regression.
**Action:** For fallback selectors, use comma-separated strings for batching to avoid unnecessary network round-trips.

## 2025-02-23 - [Playwright Concurrent Locator Evaluation]
**Learning:** Playwright's comma-separated selector grouping fails if any individual selector inherently contains a comma (e.g. `text="Sign In, Please"`), causing syntax errors. Batching multiple fallback selectors into a single comma-separated string `", ".join(selectors)` breaks the graceful fallback isolation where one malformed selector ruins the entire check.
**Action:** To optimize N+1 locator loops over network without breaking syntax or fault isolation, use `asyncio.gather(..., return_exceptions=True)` to evaluate individual selectors concurrently in a single batch, preserving the ability to ignore failures on malformed selectors.
