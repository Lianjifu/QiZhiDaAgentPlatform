"""Platform use cases."""

from qzdap.modules.platform.application.use_cases.aggregate_costs import (  # noqa: F401
    build as build_aggregate_costs,
)
from qzdap.modules.platform.application.use_cases.assign_subscription import (  # noqa: F401
    build as build_assign_subscription,
)
from qzdap.modules.platform.application.use_cases.get_plan import (  # noqa: F401
    build as build_get_plan,
)
from qzdap.modules.platform.application.use_cases.get_subscription import (  # noqa: F401
    build as build_get_subscription,
)
from qzdap.modules.platform.application.use_cases.list_plans import (  # noqa: F401
    build as build_list_plans,
)
from qzdap.modules.platform.application.use_cases.list_settings import (  # noqa: F401
    build as build_list_settings,
)
from qzdap.modules.platform.application.use_cases.upsert_setting import (  # noqa: F401
    build as build_upsert_setting,
)
