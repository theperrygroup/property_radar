# Errors And Retries

All client failures derive from `PropertyRadarError`.

```python
from property_radar import (
    AuthenticationError,
    PropertyRadarClient,
    RateLimitError,
)

try:
    with PropertyRadarClient() as client:
        client.accounts.members()
except AuthenticationError:
    refresh_credentials()
except RateLimitError as error:
    schedule_after(error.retry_after)
```

HTTP errors expose sanitized metadata:

- `status_code`
- `request_id`
- `retry_after`

The response body is not copied into the exception, which reduces the chance of
logging licensed or personal data.

## Exception map

| Condition | Exception |
| --- | --- |
| Invalid local configuration | `ConfigurationError` |
| Persistent operation not enabled | `MutationNotAllowedError` |
| Paid invocation not enabled | `ChargeNotAllowedError` |
| HTTP 400 | `BadRequestError` |
| HTTP 401 | `AuthenticationError` |
| HTTP 402 | `PaymentRequiredError` |
| HTTP 403 | `ForbiddenError` |
| HTTP 404 | `NotFoundError` |
| HTTP 409 | `ConflictError` |
| HTTP 422 | `ValidationError` |
| HTTP 429 | `RateLimitError` |
| HTTP 5xx | `ServerError` |
| Timeout | `RequestTimeoutError` |
| Other network failure | `NetworkError` |
| Invalid success payload | `InvalidResponseError` |

## Retry policy

The default is two retries after the first attempt. Safe reads retry on
timeouts, network errors, HTTP 429, and HTTP 5xx with bounded exponential
backoff. A valid `Retry-After` header takes precedence and is capped at 60
seconds; non-finite values are ignored.

Read-like POST operations opt in explicitly. Persistent mutations and paid
invocations never retry automatically because the public contract does not
document idempotency keys. After an ambiguous failure, reconcile vendor state
before repeating one of those operations.
