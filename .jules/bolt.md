## 2024-05-10 - Playwright Locator Performance

**Learning:** When retrieving text from multiple elements found by a Playwright locator, looping and calling `await items.nth(i).inner_text()` causes an N+1 query pattern leading to multiple network round-trips over the Playwright IPC.

**Action:** Use `await items.all_inner_texts()` to fetch all text in a single network round-trip, then process the local strings.
