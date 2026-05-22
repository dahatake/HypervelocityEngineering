# Cache strategy design (English fixture for semantic_paragraph eval)

## Read-Through Cache

The application reads from the cache first. On a miss, the cache layer
queries the primary datastore, populates the cache, and returns the
value. TTL is configured per key family.

We use Redis as the cache backend. Connection pools are sized to
`max(cpu_count() * 2, 16)`.

## Write-Behind Queue

Writes are accepted by the application synchronously but persisted to the
datastore asynchronously via a background worker. The queue is durable
(persisted to disk) so that crashes do not lose pending writes.

Worker pools scale with queue depth: 1 worker per 1000 queued items,
capped at 32 workers.

## Failure Modes

When the cache is unreachable, the application bypasses it and queries
the primary datastore directly. A circuit breaker prevents repeated
failed cache connections from saturating the thread pool.

Datastore outages return HTTP 503 with a Retry-After header. Idempotent
read requests retry up to 3 times with exponential backoff.
