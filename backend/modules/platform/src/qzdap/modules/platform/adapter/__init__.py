"""platform adapter layer."""

from qzdap.modules.platform.adapter.http import build_router  # noqa: F401
from qzdap.modules.platform.adapter.persistence import (  # noqa: F401
    SqlPlanRepository,
    SqlSubscriptionRepository,
    SqlTenantSettingRepository,
)
