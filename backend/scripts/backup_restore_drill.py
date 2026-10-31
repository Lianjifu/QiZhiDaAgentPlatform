#!/usr/bin/env python3
"""**备份恢复演练** —— S-36（DROP 旧表）的门禁之一 ✓。

⚠️ **「备份存在」不等于「能恢复」** ✓ —— 台账的纪律写得很死 ✓：
「**测试环境验证过不算** ✓；备份必须**恢复演练过** ✓」
（`cleanup-ledger.md` §3.1 的回退纪律第 2 条 ✓）。
所以这个脚本**真的做一遍** ✓：备份 → 恢复到一张**临时库** ✓ → **逐项核对** ✓。

核对什么 ✓（能回答「恢复出来的库是不是原来那个库」✓）：
- **迁移版本** ✓（`alembic_version` ✓ —— 恢复出来的库得在同一个版本上 ✓）；
- **表清单** ✓（不多不少 ✓）；
- **每张表的行数** ✓；
- **关键业务表的行内容校验和** ✓（`md5` 聚合 ✓ —— 行数相同但内容被换掉的
  情况也能抓到 ✓ ✓）。

用法::

    python scripts/backup_restore_drill.py --url postgresql://user:pass@host:5432/db
    python scripts/backup_restore_drill.py --url postgresql://... --keep   # 留备份文件
    python scripts/backup_restore_drill.py --url postgresql://... --dump-dir /tmp/drills

退出码：``0`` = 演练通过 ✓；``1`` = 不通过 ✗（差异打到 stderr ✓）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

#: **逐行内容校验和的表** ✓ —— 覆盖「会话 / 记忆 / 知识 / 治理」四条主线 ✓
#: （行数相同但内容被换掉的情况靠它们抓 ✓ ✓）。
DEFAULT_CHECKSUM_TABLES = (
    "agent_sessions",
    "session_turns",
    "session_messages",
    "session_events",
    "admin_memory_l2",
    "admin_knowledge_docs",
    "admin_policies",
    "users",
)


def _pg_url(url: str) -> str:
    """**asyncpg / psycopg 的 URL → libpq 的 URL** ✓（pg 工具只认后者 ✓）。"""
    parts = urlsplit(url)
    scheme = "postgresql"
    if parts.scheme.startswith("postgresql+"):
        scheme = "postgresql"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _db_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    """跑一条命令 ✓ —— 失败就把 stderr 打出来 ✓（不要静默吞掉 ✓）。"""
    proc = subprocess.run(  # noqa: S603 —— 命令是本脚本自己拼的 ✓（pg_* 工具 ✓）
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败（{proc.returncode}）：{' '.join(cmd)}\n{proc.stderr.strip()}")


def _psql(url: str, sql: str) -> str:
    """跑一条 SQL 并拿回纯文本结果 ✓。"""
    proc = subprocess.run(  # noqa: S603 —— 命令是本脚本自己拼的 ✓
        [  # noqa: S607 —— psql 在 PATH 里 ✓
            "psql",
            _pg_url(url),
            "-X",
            "-q",
            "-A",
            "-t",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"SQL 失败：{sql}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def _table_names(url: str) -> list[str]:
    out = _psql(
        url,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
    )
    return [line for line in out.splitlines() if line]


def _row_count(url: str, table: str) -> int:
    # 表名来自**本库自己的 pg_tables** ✓（不是外部输入 ✓）→ 拼进 SQL 是安全的 ✓。
    return int(_psql(url, f'SELECT count(*) FROM "{table}"') or "0")  # noqa: S608


def _checksum(url: str, table: str) -> str:
    """**整表内容的校验和** ✓（行序无关 ✓ —— 用 `md5` 排序后聚合 ✓）。"""
    return _psql(
        url,
        f"SELECT coalesce(md5(string_agg(h, '' ORDER BY h)), '') "  # noqa: S608 —— 表名来自本库 ✓
        f'FROM (SELECT md5(t::text) AS h FROM "{table}" t) s',
    )


def _alembic_version(url: str) -> str:
    out = _psql(url, "SELECT version_num FROM alembic_version LIMIT 1")
    return out or "(空)"


def _server_version_num(url: str) -> int:
    """服务器版本号（数值）✓ —— 用来判断「备份里哪些语句它不认」✓。"""
    try:
        return int(_psql(url, "SHOW server_version_num") or "0")
    except (RuntimeError, ValueError):
        return 0


def _sanitize_dump(path: Path, *, server_version: int) -> None:
    """**去掉服务器不认的那几行** ✓。

    ⚠️ **为什么需要** ✓ —— 本机的 `pg_dump` / `psql` 往往比服务器新 ✓：
    - `pg_dump` 17 会写 `SET transaction_timeout = 0` ✓ —— **PG17 才有这个参数**
      ✓ → PG16 的服务器不认 ✓ → 恢复直接失败 ✗；
    - `pg_dump` 17.10 会写 `\\restrict` / `\\unrestrict` ✓ —— **psql 17.6 之后
      才有这两个元命令** ✓ → 老 psql 不认 ✗。

    这两行都是**会话设置** ✓（去掉不影响数据 ✓）—— 去掉之后老版本工具链也能
    恢复新版本导出的备份 ✓ ✓。
    """
    if server_version >= 170000:
        return
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [
        line
        for line in lines
        if "SET transaction_timeout" not in line
        and not line.lstrip().startswith("\\restrict")
        and not line.lstrip().startswith("\\unrestrict")
    ]
    if len(kept) != len(lines):
        path.write_text("".join(kept), encoding="utf-8")
        print(f"· 去掉 {len(lines) - len(kept)} 行服务器不认的语句（PG{server_version} ✓）")


def drill(url: str, *, dump_dir: Path | None, keep: bool) -> int:
    """**做一遍演练** ✓ —— 返回退出码 ✓。"""
    source_db = _db_name(url)
    if not source_db:
        print("✗ URL 里没有库名", file=sys.stderr)
        return 1

    # 建 / 删临时库用的**维护库** URL ✓（同一个 server ✓ —— `postgres` 库几乎
    # 总是存在 ✓ —— 删的是我们自己刚建的 ✓）。
    maintenance_url = _pg_url(url).rsplit("/", 1)[0] + "/postgres"

    dump_dir = dump_dir or Path(tempfile.mkdtemp(prefix="qzdap-drill-"))
    dump_dir.mkdir(parents=True, exist_ok=True)
    dump_file = dump_dir / f"{source_db}-{uuid.uuid4().hex[:8]}.sql"
    scratch_db = f"{source_db}_drill_{uuid.uuid4().hex[:8]}"

    env = dict(os.environ)
    # pg 工具遇密码要提示 → 用 PGPASSWORD 免交互 ✓。
    password = urlsplit(url).password
    if password:
        env["PGPASSWORD"] = password

    try:
        print(f"→ 备份 {source_db} → {dump_file}")
        # ⚠️ **用纯 SQL 格式** ✓（不是 custom ✓）—— 纯文本才能**按需去掉几行**
        # ✓（见 `_sanitize_dump` ✓）→ **本机 pg_dump / psql 比服务器新时也能跑**
        # ✓。
        _run(
            [
                "pg_dump",
                "--format=plain",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(dump_file),
                _pg_url(url),
            ],
            env=env,
        )
        _sanitize_dump(dump_file, server_version=_server_version_num(url))
        if not dump_file.exists() or dump_file.stat().st_size == 0:
            print("✗ 备份文件是空的", file=sys.stderr)
            return 1
        print(f"✓ 备份完成（{dump_file.stat().st_size} 字节）")

        print(f"→ 恢复到临时库 {scratch_db}")
        _run(
            [
                "createdb",
                "--maintenance-db",
                maintenance_url,
                scratch_db,
            ],
            env=env,
        )
        # ⚠️ **`ON_ERROR_STOP=1`** ✓ —— 恢复过程里任何 SQL 错误都要**当场失败**
        # ✓（不然后面只靠内容比对才知道恢复坏了 ✗ —— 慢且不直接 ✗）。
        _run(
            [
                "psql",
                "--dbname",
                _pg_url(url).rsplit("/", 1)[0] + "/" + scratch_db,
                "-v",
                "ON_ERROR_STOP=1",
                "-q",
                "-f",
                str(dump_file),
            ],
            env=env,
        )
        scratch_url = url.rsplit("/", 1)[0] + "/" + scratch_db
        print("✓ 恢复完成")

        print("→ 核对")
        problems: list[str] = []

        src_version = _alembic_version(url)
        dst_version = _alembic_version(scratch_url)
        if src_version != dst_version:
            problems.append(f"迁移版本不一致：源 {src_version} ≠ 恢复 {dst_version}")
        else:
            print(f"✓ 迁移版本一致（{src_version}）")

        src_tables = _table_names(url)
        dst_tables = _table_names(scratch_url)
        only_src = sorted(set(src_tables) - set(dst_tables))
        only_dst = sorted(set(dst_tables) - set(src_tables))
        if only_src or only_dst:
            problems.append(f"表清单不一致：源多 {only_src} / 恢复多 {only_dst}")
        else:
            print(f"✓ 表清单一致（{len(src_tables)} 张）")

        for table in src_tables:
            src_count = _row_count(url, table)
            dst_count = _row_count(scratch_url, table)
            if src_count != dst_count:
                problems.append(f"行数不一致：{table} 源 {src_count} ≠ 恢复 {dst_count}")
        print(f"✓ 行数逐表核对完成（{len(src_tables)} 张）")

        checked = [t for t in DEFAULT_CHECKSUM_TABLES if t in src_tables and t in dst_tables]
        for table in checked:
            src_sum = _checksum(url, table)
            dst_sum = _checksum(scratch_url, table)
            if src_sum != dst_sum:
                problems.append(f"内容校验和不一致：{table}")
        if checked:
            print(f"✓ 内容校验和核对完成（{len(checked)} 张关键表）")

        if problems:
            print("\n✗ 演练不通过：", file=sys.stderr)
            for item in problems:
                print(f"  - {item}", file=sys.stderr)
            return 1

        print("\n✓ 备份恢复演练通过：恢复出来的库与源库一致")
        return 0
    finally:
        # 临时库一定要删 ✓ —— 不然开发库里会堆一堆 drill 库 ✗。
        try:
            _run(
                [
                    "dropdb",
                    "--if-exists",
                    "--maintenance-db",
                    maintenance_url,
                    scratch_db,
                ],
                env=env,
            )
            print(f"✓ 临时库 {scratch_db} 已清理")
        except Exception as exc:  # pragma: no cover - 清理失败不该盖掉演练结论
            print(f"⚠️ 临时库 {scratch_db} 清理失败：{exc}", file=sys.stderr)
        if not keep:
            dump_file.unlink(missing_ok=True)
            print("✓ 备份文件已删除（要留就加 --keep）")
        else:
            print(f"· 备份文件保留在 {dump_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="备份恢复演练（S-36 的门禁之一）")
    parser.add_argument(
        "--url",
        default=os.environ.get("QZDAP_DATABASE_URL"),
        help="要演练的库（默认取 QZDAP_DATABASE_URL）",
    )
    parser.add_argument("--dump-dir", default=None, help="备份文件放哪（默认临时目录）")
    parser.add_argument("--keep", action="store_true", help="演练完保留备份文件")
    args = parser.parse_args()
    if not args.url:
        print("✗ 要么给 --url，要么设 QZDAP_DATABASE_URL", file=sys.stderr)
        return 1
    dump_dir = Path(args.dump_dir) if args.dump_dir else None
    return drill(args.url, dump_dir=dump_dir, keep=args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
