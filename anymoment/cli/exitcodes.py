"""Process exit codes for the AnyMoment CLI.

0 ok
2 usage (bad arguments, 400, 422)
3 auth (401, unverified email, missing token)
4 not found
5 conflict
6 rate limited
7 remote or sync error (403, 5xx, network, CalDAV failures)
"""

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_CONFLICT = 5
EXIT_RATE_LIMIT = 6
EXIT_REMOTE = 7

EXIT_CODE_NAMES = {
    EXIT_OK: "ok",
    EXIT_USAGE: "usage",
    EXIT_AUTH: "auth",
    EXIT_NOT_FOUND: "not_found",
    EXIT_CONFLICT: "conflict",
    EXIT_RATE_LIMIT: "rate_limited",
    EXIT_REMOTE: "remote",
}
