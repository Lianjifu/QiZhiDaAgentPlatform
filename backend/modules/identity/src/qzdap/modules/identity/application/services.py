"""Top-level identity service — wires the use cases + ports for the
composition root.

The composition root instantiates this with concrete adapters and passes it
to `router.py` which wires use cases to FastAPI routes.
"""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.identity.application.ports import (
    AccessTokenIssuer,
    APIKeyRepository,
    Hasher,
    TenantRepository,
    UserRepository,
    WorkspaceRepository,
)
from qzdap.modules.identity.application.use_cases.auth.login import LoginUseCase
from qzdap.modules.identity.application.use_cases.create_tenant import (
    CreateTenantUseCase,
)
from qzdap.modules.identity.application.use_cases.create_workspace import (
    CreateWorkspaceUseCase,
)
from qzdap.modules.identity.application.use_cases.issue_api_key import (
    IssueAPIKeyUseCase,
)
from qzdap.modules.identity.application.use_cases.register_user import (
    RegisterUserUseCase,
)
from qzdap.modules.identity.application.use_cases.revoke_api_key import (
    RevokeAPIKeyUseCase,
)


@dataclass(slots=True)
class IdentityService:
    tenants: TenantRepository
    workspaces: WorkspaceRepository
    users: UserRepository
    api_keys: APIKeyRepository
    hasher: Hasher
    issuer: AccessTokenIssuer

    def create_tenant(self) -> CreateTenantUseCase:
        return CreateTenantUseCase(self.tenants)

    def create_workspace(self) -> CreateWorkspaceUseCase:
        return CreateWorkspaceUseCase(self.tenants, self.workspaces)

    def register_user(self) -> RegisterUserUseCase:
        return RegisterUserUseCase(self.tenants, self.users, self.hasher)

    def issue_api_key(self) -> IssueAPIKeyUseCase:
        return IssueAPIKeyUseCase(self.users, self.api_keys, self.hasher)

    def revoke_api_key(self) -> RevokeAPIKeyUseCase:
        return RevokeAPIKeyUseCase(self.api_keys)

    def login(self) -> LoginUseCase:
        return LoginUseCase(self.users, self.hasher, self.issuer, self.workspaces)
