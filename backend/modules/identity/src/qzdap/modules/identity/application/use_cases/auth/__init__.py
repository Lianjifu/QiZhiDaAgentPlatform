"""Auth use cases — login (password-based credential auth).

Lives under ``use_cases/auth/`` so login can evolve independently of user/
tenant/api_key business logic. Out of scope today: MFA, refresh tokens,
logout — see the login refactor plan for context.
"""

from .login import LoginResult, LoginUseCase

__all__ = ["LoginResult", "LoginUseCase"]