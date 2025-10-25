# Laboratory 2 Report:

## 1. Performance Comparison Between Single-threaded and Multi-threaded Servers

### 1.1 Single-threaded Server Performance

The single-threaded server was tested at `http://localhost:5000` with 50 concurrent requests. The server successfully processed all requests with a total execution time of 3.12 seconds.

### 1.2 Multi-threaded Server Performance

The multi-threaded server was tested at `http://localhost:5001` under identical conditions (50 concurrent requests). All requests completed successfully in 2.12 seconds.

### 1.3 Performance Analysis

The multi-threaded implementation demonstrated a speedup of 1.47x compared to the single-threaded version, representing a 31.8% performance improvement. The time saved was 0.99 seconds for this test configuration, confirming that multithreading provides measurable benefits when handling concurrent requests.

```
Old (single-threaded): ████████████████████████████████████████ 3.12s
New (multithreaded)  : ███████████████████████████░░░░░░░░░░░░░ 2.12s
```

## 2. Hit Counter and Race Condition

### 2.1 Triggering the Race Condition

A race condition was deliberately triggered by launching 20 threads, each sending 5 requests concurrently to the server running in unsafe mode (`--unsafe` flag enabled). The test generated 100 total requests targeting `/test.txt`.

The test completed in 10.25 seconds with all 100 requests succeeding. However, the final counter value was 31 instead of the expected 100, resulting in 69 lost increments. This demonstrates the classic race condition problem in concurrent programming.

### 2.2 Code Responsible for Race Condition

```python
old = COUNTERS.get(rel_path, 0)     # Step 1: Read
time.sleep(0.001)                    # Step 2: Artificial delay
COUNTERS[rel_path] = old + 1         # Step 3: Write
```

The race condition occurs because multiple threads can read the same counter value before any thread writes back the incremented value. The artificial delay magnifies this issue by increasing the window where multiple threads operate on stale data.

### 2.3 Fixed Implementation

```python
with counters_lock:
    old = COUNTERS.get(rel_path, 0)
    COUNTERS[rel_path] = old + 1
    print(f"[COUNTER] {rel_path}: {old} -> {old+1}")
```

The solution uses a lock-based mutual exclusion mechanism. The `with counters_lock` statement ensures that only one thread can execute the critical section at a time, preventing concurrent access to the shared counter data structure.

## 3. Rate Limiting

### 3.1 Request Spam Configuration

The rate limiting functionality was tested by sending requests at 20 requests per second to `http://localhost:5000`. The test ran for 10 seconds, generating 200 total requests.

### 3.2 Response Statistics

The server enforced its rate limit effectively across the test duration. Sample output shows the distribution of responses:

```
[  0s] R/s total= 20  success=  5  denied= 15  other=  0  errors=  0
[  1s] R/s total= 20  success=  5  denied= 15  other=  0  errors=  0
[  2s] R/s total= 20  success=  5  denied= 15  other=  0  errors=  0
```

Over the complete 10-second test period, the server returned 15 successful responses (HTTP 2xx) and 185 denied responses (HTTP 429), with no network errors or other response types. This demonstrates consistent rate limit enforcement with approximately 5 successful requests per second allowed.

### 3.3 IP-based Rate Limiting

The rate limiting implementation tracks requests on a per-IP basis. When multiple clients send requests from different IP addresses, each IP address maintains its own rate limit quota independently. This prevents one client from exhausting the server's capacity and ensures fair resource distribution across multiple clients.