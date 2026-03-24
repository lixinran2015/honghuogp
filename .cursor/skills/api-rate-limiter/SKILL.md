---
name: api-rate-limiter
description: Handle API rate limiting for Tushare and other financial data APIs. Use when implementing API clients, batch data fetching, or when encountering rate limit errors. Implements token bucket algorithm and retry mechanisms.
---

# API Rate Limiter

Handles rate limiting for financial data APIs, especially Tushare API (200 calls/minute limit).

## Implementation Pattern

### Rate Limiter Class

```python
import threading
import time

class RateLimiter:
    def __init__(self, max_calls: int = 200, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        with self.lock:
            now = time.time()
            # Remove expired calls
            self.calls = [t for t in self.calls if now - t < self.period]
            
            if len(self.calls) >= self.max_calls:
                oldest_call = min(self.calls)
                wait_time = self.period - (now - oldest_call) + 0.1
                if wait_time > 0:
                    time.sleep(wait_time)
                    # Re-clean after wait
                    now = time.time()
                    self.calls = [t for t in self.calls if now - t < self.period]
            
            self.calls.append(time.time())
```

### Usage in Batch Operations

```python
rate_limiter = RateLimiter(max_calls=200, period=60.0)

def fetch_with_limit(ts_code: str):
    rate_limiter.wait_if_needed()
    return api_call(ts_code)
```

### Error Handling with Retry

```python
def fetch_with_retry(ts_code: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            rate_limiter.wait_if_needed()
            return api_call(ts_code)
        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 60  # Wait full minute
                time.sleep(wait_time)
                continue
            raise
```

## Best Practices

1. **Always check rate limits before API calls**
2. **Use threading.Lock() for thread safety**
3. **Add 0.1s buffer to avoid edge cases**
4. **Log rate limit waits for debugging**
5. **Implement exponential backoff for retries**

## Tushare Specific

- Limit: 200 calls/minute
- Use 3-5 concurrent workers max
- Add delays between batches (0.1-0.5s)
- Monitor for "每分钟最多访问该接口200次" error
