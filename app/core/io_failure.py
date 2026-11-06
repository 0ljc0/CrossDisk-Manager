"""Write failure disposition; a publication attempt always needs recovery review."""
import errno


def disposition(error, *, publication_attempted):
    if not isinstance(error, OSError):
        raise TypeError("Expected an operating-system I/O error")
    return dict(status="NEEDS_RECOVERY" if publication_attempted else "FAILED_STOPPED",
                error_number=error.errno, no_space=error.errno == errno.ENOSPC,
                automatic_retry_allowed=False, continue_later_operations=False)
