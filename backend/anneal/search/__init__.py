"""Literature search adapters.

Adapters return plain neutral "paper-like" dicts (NOT domain models).
Mapping dicts -> Anneal's native Material model lives in the service layer
(``anneal.services.collect_service``), keeping the fetcher pure and the
domain side native.

The multi-source orchestrator (``search_all``) and the pure ``dedupe`` helper
are re-exported here for convenient import.
"""

from anneal.search.dedupe import dedupe
from anneal.search.multi import DEFAULT_SOURCES, REGISTRY, search_all

__all__ = ["dedupe", "search_all", "DEFAULT_SOURCES", "REGISTRY"]
