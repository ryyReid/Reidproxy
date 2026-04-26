## 2025-04-26 - HTML Rewrite Double-Prefixing Anti-pattern
**Learning:** Sequential regular expression rewriting of individual HTML attributes (e.g., matching `src` before `data-lazy-src`) without word boundaries causes a double-prefixing bug due to substring overlaps (matching `src=` inside `data-lazy-src=`). This also severely degrades performance by creating multiple on-the-fly regex compilations per request.
**Action:** Always use a combined, pre-compiled regex with word boundaries (e.g., `\b(href|src|data-lazy-src)`) for safety, correctness, and O(1) compilation performance.
