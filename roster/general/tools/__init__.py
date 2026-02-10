"""General butler tools — freeform entity and collection management.

Re-exports all public symbols so that ``from butlers.tools.general import X``
continues to work as before.
"""

from butlers.tools.general._helpers import _deep_merge
from butlers.tools.general.collections import (
    collection_create,
    collection_delete,
    collection_export,
    collection_list,
)
from butlers.tools.general.entities import (
    entity_create,
    entity_delete,
    entity_get,
    entity_search,
    entity_update,
)

__all__ = [
    "_deep_merge",
    "collection_create",
    "collection_delete",
    "collection_export",
    "collection_list",
    "entity_create",
    "entity_delete",
    "entity_get",
    "entity_search",
    "entity_update",
]
