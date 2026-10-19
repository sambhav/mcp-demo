# Checklist

## Correctness
- Off-by-one, null/undefined, empty collections, error paths
- Concurrency: shared state, ordering, retries that are not idempotent

## Security
- Untrusted input reaching a shell, SQL, a path, HTML or a deserializer
- Secrets in code, logs or error messages
- AuthZ checked on the server side, not only in the UI

## Tests
- New behaviour has a test that fails without the change
- Edge cases above are covered or explicitly out of scope

## Readability
- Names say what, comments say why
- No dead code, no commented-out code
