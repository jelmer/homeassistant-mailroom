"""Constants for the mailroom integration."""

from datetime import timedelta

DOMAIN = "mailroom"

# mailroom reads its records from local disk on every request, so asking
# often is cheap. Its own carrier polling runs on a much longer interval.
UPDATE_INTERVAL = timedelta(minutes=5)
