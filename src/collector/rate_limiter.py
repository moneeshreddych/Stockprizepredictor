import time

class TokenBucket:
    """Simple token bucket rate limiter.

    Allows a maximum number of tokens (requests) per interval.
    Tokens are regenerated at a constant rate.
    """
    def __init__(self, max_tokens: int, refill_interval_seconds: int):
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.refill_interval = refill_interval_seconds
        self.last_refill = time.time()

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        # Add tokens proportional to elapsed time
        tokens_to_add = int((elapsed / self.refill_interval) * self.max_tokens)
        if tokens_to_add > 0:
            self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
            self.last_refill = now

    def consume(self, amount: int = 1) -> bool:
        """Consume tokens if enough are available.

        Returns True if the requested amount was consumed, otherwise False.
        """
        self._refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False
