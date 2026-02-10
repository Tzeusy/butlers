"""Routing tools — message classification, routing, dispatch, and aggregation."""

from butlers.tools.switchboard.routing.classify import (
    classify_message,
)
from butlers.tools.switchboard.routing.dispatch import (
    ButlerResult,
    aggregate_responses,
    dispatch_decomposed,
)
from butlers.tools.switchboard.routing.route import (
    post_mail,
    route,
)

__all__ = [
    "ButlerResult",
    "aggregate_responses",
    "classify_message",
    "dispatch_decomposed",
    "post_mail",
    "route",
]
