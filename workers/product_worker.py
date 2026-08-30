"""
DEPRECATED — superseded by the multi-tenant flow.

Product creation no longer goes through a Redis queue consumed by a
single-tenant worker with one global WordPress site. It now happens
synchronously inside workers/common_handlers.py, scoped to whichever
tenant's site is connected, via clients/site_connector_client.py talking
to that site's ODview Sync plugin.

This file is kept only so old deploy configs referencing it fail loudly
and clearly instead of crashing on a stale Config attribute or a
ProductBuilder signature that no longer matches. Do not add this back to
Procfile / railway.yaml — it isn't needed anymore.
"""
import sys

if __name__ == "__main__":
    sys.exit(
        "workers/product_worker.py is deprecated and does nothing.\n"
        "Product creation now happens directly in workers/common_handlers.py\n"
        "(triggered by the bot conversation, per-tenant). Remove any process\n"
        "manager entry that still starts this file."
    )
