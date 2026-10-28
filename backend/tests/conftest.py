"""backend/tests 的 conftest.

把 ``tests/shared/fixtures.py`` 里的 fixture 接进来 —— 否则那个文件里的
autouse fixture (``_ensure_qzdap_env``) 只有被显式 import 的那个子树
才吃得到, 这里等于白写.
"""

from shared.fixtures import *  # noqa: F403
