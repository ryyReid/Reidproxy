## 2024-05-18 - HTML Regex Rewriting Bug and Bottleneck
**Learning:** In the proxy HTML rewriting logic (`app.py`), sequentially iterating over an array of attributes (e.g., `['href', 'src', 'data-src']`) and running separate regex replacements creates two major issues:
1. **Performance bottleneck:** It causes O(N*M) regex passes over the entire HTML string, where N is the number of attributes and M is the type of URL matched.
2. **Double-rewrite Bug:** Because `src` is matched before `data-src`, the `src` pass matches the substring inside `data-src="/path"`, turning it into `data-src="/proxy/path"`. Then the `data-src` pass matches it *again*, creating a broken URL (`data-src="/proxy/proxy/path"`).

**Action:** Always combine HTML attribute rewrites into a single, pre-compiled global regex utilizing word boundaries `\b(href|src|data-src)` to prevent both the performance bottleneck and the overlapping substring bug.
