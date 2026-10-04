"""QZDAP secrets vault.

Resolves ``ref`` strings (e.g. ``env:KEY_NAME``) to secret material.
P5 ships env / file / noop backends; P10+ adds HashiCorp Vault (hvac)
and Vault CSI driver mounts for production-grade secret delivery.
"""

from __future__ import annotations

from qzdap_vault.actor import ActorContext
from qzdap_vault.crypto import (
    CryptoError,
    InvalidCiphertext,
    InvalidKey,
    decrypt,
    derive_key,
    encrypt,
    generate_key,
)
from qzdap_vault.csi_vault import CSIVaultSecretsResolver
from qzdap_vault.env_vault import EnvVaultSecretsResolver
from qzdap_vault.errors import (
    InvalidSecretRef,
    SecretAccessDenied,
    SecretNotFound,
    VaultError,
)
from qzdap_vault.file_vault import FileVaultSecretsResolver
from qzdap_vault.hashicorp_vault import HashicorpVaultSecretsResolver
from qzdap_vault.no_op import NoOpSecretsResolver
from qzdap_vault.resolver import (
    SecretRef,
    VaultSecretsResolver,
    parse_ref,
    resolve_value,
)

__all__ = [
    "ActorContext",
    "CSIVaultSecretsResolver",
    "CryptoError",
    "EnvVaultSecretsResolver",
    "FileVaultSecretsResolver",
    "HashicorpVaultSecretsResolver",
    "InvalidCiphertext",
    "InvalidKey",
    "InvalidSecretRef",
    "NoOpSecretsResolver",
    "SecretAccessDenied",
    "SecretNotFound",
    "SecretRef",
    "VaultError",
    "VaultSecretsResolver",
    "decrypt",
    "derive_key",
    "encrypt",
    "generate_key",
    "parse_ref",
    "resolve_value",
]
