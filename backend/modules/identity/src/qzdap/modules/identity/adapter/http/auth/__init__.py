"""HTTP adapter: auth subpackage (login).

Lives under ``adapter/http/auth/`` so login contract changes stay scoped
to one folder — separate from user/tenant/api_key DTOs and routers.
"""

from qzdap.modules.identity.adapter.http.auth import dto, router

__all__ = ["dto", "router"]