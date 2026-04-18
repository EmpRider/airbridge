## 2025-04-18 - Playwright N+1 Element Interaction Anti-Pattern
**Learning:** Calling `await item.inner_text()` inside a loop over Playwright locator elements causes N+1 asynchronous round-trips to the browser context, which becomes a severe bottleneck for lists/menus.
**Action:** When extracting text or attributes from multiple elements, fetch them all at once using `await items.all_inner_texts()` (or `evaluateAll()`) to reduce browser communication to O(1) before iterating in Python.
