"""Literature search adapters.

Adapters return plain neutral "paper-like" dicts (NOT domain models).
Mapping dicts -> Anneal's native Material model lives in the service layer
(``anneal.services.collect_service``), keeping the fetcher pure and the
domain side native.
"""
