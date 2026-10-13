## 2026-10-11 - Vectorized string concatenation & regex caching for DataFrame phone parsing

**Learning:** In pandas, using `df[fields].agg(' '.join, axis=1)` executes row-by-row Python string joins across DataFrame columns, introducing significant overhead on large dataset imports. Replacing `.agg(' '.join, axis=1)` with vectorized column addition (`df[a] + " " + df[b]`) eliminates row-wise Python iteration.

When extracting country info from phone numbers, repeated regex pattern matching across duplicate phone values further consumes CPU time. Caching lookups via a dictionary (`country_cache`) avoids redundant regex parsing.

**Measured Impact (Sample CRM Dataset - 163,974 rows):**
- Country extraction stage: Reduced execution time from 3.06s to 0.53s (~5.8x speedup).
- Overall `audit.py` execution time: Reduced total pipeline run time from ~6.1s to ~3.1s (~2.0x speedup).

**Benchmark Measurements (50,000 synthetic rows, Python 3.12, Pandas 3.0.6):**
- Unique-heavy dataset (50,000 distinct phone numbers): Median time reduced from 3.32s to 0.39s (~8.4x speedup due to vectorized concatenation; cache size ~4.5 MB).
- Duplicate-heavy dataset (10 distinct phone numbers): Median time reduced from 3.45s to 0.05s (~63x speedup due to vectorization + memoization; cache size ~1 KB).

**Action:** Prefer vectorized Series string operations over `df.agg(..., axis=1)` or `df.apply(..., axis=1)`. When mapping functions with non-trivial parsing logic across Series containing duplicate string values, memoize function outputs in a dictionary to eliminate redundant parsing.
