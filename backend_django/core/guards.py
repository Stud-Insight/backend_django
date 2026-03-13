"""Reusable guards for API endpoints."""


def check_period_not_archived(period) -> tuple | None:
    """
    Check that a period is not archived. Returns an error response tuple if archived, None otherwise.

    Usage in an endpoint:
        error = check_period_not_archived(period)
        if error:
            return error
    """
    from .exceptions import ArchivedError

    if hasattr(period, "status") and period.status == "archived":
        return ArchivedError(
            "Impossible de modifier des données archivées. "
            f"La période « {period.name} » est archivée."
        ).to_response()
    return None
