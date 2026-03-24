---
name: performance-optimizer
description: Optimize code performance for data processing, database queries, and API calls. Use when code is slow, processing large datasets, or when optimizing ETL pipelines and data warehouse operations.
---

# Performance Optimizer

Optimize code performance for data processing and database operations.

## Database Query Optimization

### Use Indexes

```python
# Ensure indexes exist for frequently queried fields
# Example: Index on ts_code and end_date for financial data
CREATE INDEX idx_fact_fundamental_ts_code_end_date 
ON fact_fundamental(ts_code, end_date);
```

### Batch Queries Instead of Loops

```python
# ❌ BAD: N+1 query problem
for ts_code in ts_codes:
    data = session.query(Model).filter(Model.ts_code == ts_code).first()

# ✅ GOOD: Single query
all_data = session.query(Model).filter(
    Model.ts_code.in_(ts_codes)
).all()
data_dict = {item.ts_code: item for item in all_data}
```

### Use Bulk Operations

```python
# ❌ BAD: Individual inserts
for record in records:
    session.add(Model(**record))
    session.commit()

# ✅ GOOD: Bulk insert
session.bulk_insert_mappings(Model, records)
session.commit()
```

## API Call Optimization

### Batch API Calls

```python
# ❌ BAD: Individual calls
for ts_code in ts_codes:
    data = api.get_data(ts_code)

# ✅ GOOD: Batch calls
batch_data = api.batch_get_data(ts_codes)
```

### Concurrent Processing

```python
from concurrent.futures import ThreadPoolExecutor

def fetch_concurrent(items: list, max_workers: int = 5):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(fetch_item, items))
    return results
```

### Rate Limiting

```python
# Always implement rate limiting for API calls
rate_limiter = RateLimiter(max_calls=200, period=60.0)
for item in items:
    rate_limiter.wait_if_needed()
    fetch_item(item)
```

## Memory Optimization

### Process in Chunks

```python
# For large datasets, process in chunks
CHUNK_SIZE = 1000
for i in range(0, len(large_list), CHUNK_SIZE):
    chunk = large_list[i:i+CHUNK_SIZE]
    process_chunk(chunk)
    # Clear references if needed
    del chunk
```

### Use Generators

```python
# ✅ GOOD: Generator for large datasets
def process_large_dataset():
    for item in large_dataset:
        yield process_item(item)

# Instead of loading all into memory
```

## Code Profiling

### Identify Bottlenecks

```python
import cProfile
import pstats

def profile_function(func, *args, **kwargs):
    profiler = cProfile.Profile()
    profiler.enable()
    result = func(*args, **kwargs)
    profiler.disable()
    
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)  # Top 10 slowest functions
    
    return result
```

## Common Optimizations

### 1. Database Session Management

```python
# ✅ GOOD: Reuse session, commit in batches
session = get_session()
try:
    for batch in batches:
        process_batch(session, batch)
        session.commit()
finally:
    session.close()
```

### 2. Reduce Logging Overhead

```python
# ❌ BAD: Log every item
for item in items:
    logger.info(f"Processing {item}")

# ✅ GOOD: Log periodically
for i, item in enumerate(items):
    if i % 100 == 0:
        logger.info(f"Processed {i}/{len(items)}")
    process_item(item)
```

### 3. Cache Repeated Queries

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_stock_info(ts_code: str):
    return query_stock_info(ts_code)
```

## Performance Checklist

- [ ] Use batch queries instead of loops
- [ ] Implement bulk database operations
- [ ] Add appropriate indexes
- [ ] Use concurrent processing where safe
- [ ] Implement rate limiting for APIs
- [ ] Process large datasets in chunks
- [ ] Reduce logging frequency
- [ ] Cache frequently accessed data
- [ ] Profile code to find bottlenecks
