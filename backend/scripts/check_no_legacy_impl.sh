#!/usr/bin/env bash
# 扫描「旧实现是否已清理」—— **规则表的唯一来源**是
# docs/refactor/session-architecture/cleanup-ledger.md §3.1
# （改规则先改那里；本脚本是它的可执行形态）。
#
# 用法：
#   bash scripts/check_no_legacy_impl.sh              # 跑**已启用**的全部规则
#   bash scripts/check_no_legacy_impl.sh --stage G    # 只跑 Gateway 段
#   bash scripts/check_no_legacy_impl.sh --self-test  # 自检（扫描器本身对不对）
#
# ⚠️ 必须排除 tests/：单测会引用被删的符号，不排除则脚本永远红、必然被绕过。
# ⚠️ 一律用 grep -E（ERE）：macOS 自带的 BSD grep 在 BRE 下**不支持** `\|` 分支，
#    而 GNU grep 支持 —— 同一个脚本在开发机与 CI 上行为不一致，比没有脚本更危险。
# ⚠️ **注释行不算命中** —— 清理记录本身要写明「旧的 X 已删除」，那正是注释里的
#    `X` 在。如果注释也算命中，这条规则永远红，必然被绕过。
#    活引用一定在代码里（不在以 `#` 开头的行里）。
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/backend"

usage() {
  cat <<'USAGE'
用法：check_no_legacy_impl.sh [--stage <S>] [--self-test]

  --stage S     只跑某一阶段的规则（G / R / X / C / M / A）
  --self-test   自检：在临时目录上验证扫描器「干净目录通过、脏目录失败」
USAGE
}

# 扫描一个目录，命中即返回非零。
_scan() {  # $1=ERE pattern  $2=目录  $3=编号
  local hits
  hits="$(grep -rEn --include='*.py' -- "$1" "$2" 2>/dev/null \
    | grep -v '/tests/' \
    | grep -Ev ':[0-9]+:[[:space:]]*#' \
    || true)"
  if [ -n "$hits" ]; then
    echo "✗ $3 未清理：$1"
    echo "$hits"
    return 1
  fi
  return 0
}

_self_test() {
  # ⚠️ 不能是 local —— EXIT trap 在函数返回后才跑，local 变量那时已出作用域。
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/clean" "$tmp/dirty"
  printf 'def ok():\n    return 1\n' > "$tmp/clean/a.py"
  printf 'LEGACY_NAME = 1\n' > "$tmp/dirty/a.py"

  local failed=0
  if _scan "LEGACY_NAME" "$tmp/clean" "SELF" >/dev/null 2>&1; then
    echo "✓ 自检：干净目录通过"
  else
    echo "✗ 自检：干净目录**不该**命中"; failed=1
  fi
  if _scan "LEGACY_NAME" "$tmp/dirty" "SELF" >/dev/null 2>&1; then
    echo "✗ 自检：脏目录**应该**命中"; failed=1
  else
    echo "✓ 自检：脏目录失败"
  fi
  # 注释行不算命中。
  printf 'def ok():\n    return 1\n# LEGACY_NAME\n' > "$tmp/clean/b.py"
  if _scan "LEGACY_NAME" "$tmp/clean" "SELF" >/dev/null 2>&1; then
    echo "✓ 自检：注释行不算命中"
  else
    echo "✗ 自检：注释行**不该**算命中"; failed=1
  fi
  # ERE 分支（pattern 里带 |）必须能匹配。
  if _scan "ALPHA|BETA" "$tmp/dirty" "SELF" >/dev/null 2>&1; then
    echo "✓ 自检：ERE 分支可匹配"
  else
    echo "✗ 自检：ERE 分支**不该**漏匹配"; failed=1
  fi
  return "$failed"
}

STAGE=""
SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --stage)
      STAGE="${2:-}"; shift 2 ;;
    --stage=*)
      STAGE="${1#--stage=}"; shift ;;
    --self-test)
      SELF_TEST=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "未知参数：$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "$SELF_TEST" -eq 1 ]; then
  _self_test
  exit $?
fi

# ── 规则表 ────────────────────────────────────────────────────────────────
# 格式：pattern;目录;台账编号;阶段;状态
#   状态 on  = 已启用（命中即失败）—— 旧实现已删，这条规则开始守门
#   状态 off = 尚未启用 —— 旧实现还在场（阶段未到，或被其它层阻塞）
#
# ⚠️ 分隔符用 ``;`` 不用 ``|`` —— pattern 里可能有 ``|``（ERE 的分支）。
#    解析时**从右往左**取最后四列（目录 / 编号 / 阶段 / 状态），其余全是
#    pattern；列数不对必须**响亮地失败**（「规则没生效」不能被误读成
#    「已清理」）。
# ⚠️ 纪律（台账 §3.1.1）：规则必须**逐条绑定到具体符号**，不许用宽泛的类型名；
#    新增旧实现时，**同一个 PR 里**加规则（状态 off）。
enabled=0
skipped=0
failed=0
while IFS= read -r rule; do
  [ -z "$rule" ] && continue
  case "$rule" in \#*) continue ;; esac
  status="${rule##*;}"
  head="${rule%;*}"
  stage="${head##*;}"
  head="${head%;*}"
  entry="${head##*;}"
  head="${head%;*}"
  dir="${head##*;}"
  pattern="${head%;*}"
  if [ -z "$pattern" ] || [ -z "$dir" ] || [ -z "$entry" ]; then
    echo "✗ 规则表格式错（至少要 pattern;目录;编号;阶段;状态）：$rule" >&2
    exit 2
  fi
  if [ "$status" != "on" ]; then
    skipped=$((skipped + 1))
    continue
  fi
  if [ -n "$STAGE" ] && [ "$stage" != "$STAGE" ]; then
    skipped=$((skipped + 1))
    continue
  fi
  enabled=$((enabled + 1))
  if ! _scan "$pattern" "$dir" "$entry"; then
    failed=1
  fi
done <<'RULES_EOF'
recent_request_ids;modules/;G1;G;on
record_request_id;modules/;G1;G;on
class ParsedMessage;modules/;G4;G;on
ChannelMessageReceived;modules/;G5;G;on
SYSTEM_USER_ID|SYSTEM_AGENT_ID;modules/;G3;G;on
_verify_signature;modules/channel/;G2;G;on
OrderedDict;modules/channel/;G6;G;on
@router\.(get|post|put|delete|patch)\("/v1/sessions;modules/;G7/G8;G;on
dispatch_subscriber;modules/;G9;G;off
record_legacy_call\("R2"\);modules/;R2;R;on
(code|reason_code|error_code)\s*=\s*"(CHANNEL_NOT_FOUND|CHANNEL_DISABLED|INBOUND_ADAPTER_MISSING|OUTBOUND_ADAPTER_MISSING|WEBHOOK_SIGNATURE_INVALID|WEBHOOK_TIMESTAMP_SKEW|DUPLICATE_REQUEST|TENANT_DENIED|CHANNEL_SERVICE_ACCOUNT_MISSING|CHANNEL_DELIVERY_FAILED|IDENTITY_REJECTED|IDENTITY_CREDENTIALS_MISSING|TOKEN_INVALID|TOKEN_EXPIRED|SERVICE_ACCOUNT_NOT_CONFIGURED)";modules/;G12;G;on
(code|reason_code|error_code)\s*=\s*"(CHANNEL_NOT_FOUND|CHANNEL_DISABLED|INBOUND_ADAPTER_MISSING|OUTBOUND_ADAPTER_MISSING|WEBHOOK_SIGNATURE_INVALID|WEBHOOK_TIMESTAMP_SKEW|DUPLICATE_REQUEST|TENANT_DENIED|CHANNEL_SERVICE_ACCOUNT_MISSING|CHANNEL_DELIVERY_FAILED|IDENTITY_REJECTED|IDENTITY_CREDENTIALS_MISSING|TOKEN_INVALID|TOKEN_EXPIRED|SERVICE_ACCOUNT_NOT_CONFIGURED)";libs/;G12;G;on
(code|reason_code|error_code)\s*=\s*"(CHANNEL_NOT_FOUND|CHANNEL_DISABLED|INBOUND_ADAPTER_MISSING|OUTBOUND_ADAPTER_MISSING|WEBHOOK_SIGNATURE_INVALID|WEBHOOK_TIMESTAMP_SKEW|DUPLICATE_REQUEST|TENANT_DENIED|CHANNEL_SERVICE_ACCOUNT_MISSING|CHANNEL_DELIVERY_FAILED|IDENTITY_REJECTED|IDENTITY_CREDENTIALS_MISSING|TOKEN_INVALID|TOKEN_EXPIRED|SERVICE_ACCOUNT_NOT_CONFIGURED)";runtimes/;G12;G;on
build_session_key;runtimes/;R4;R;on
try_claim;modules/;R3;R;on
def from_url\(url: str\);runtimes/;X20;X;on
from langgraph\.checkpoint\.postgres import;runtimes/;X20;X;on
from langgraph\.checkpoint\.postgres import;modules/;X20;X;on
from langgraph\.checkpoint\.postgres import;composition/;X20;X;on
RunTurnCompletionUseCase;modules/;X2;X;off
use_cases.run_turn;modules/;X2;X;off
wait_status;modules/;X6;X;off
graph_state;modules/;X3;X;off
agent_turns;modules/;X4;X;off
agent_session_messages;modules/;X4;X;off
_fail_turn;modules/;X18;X;on
_publish_chunk;modules/;X18;X;on
compact.py;modules/;X9;C;off
_load_messages;modules/;X8;C;off
build_system_prompt;modules/;X10;C;off
layered.py;modules/;X12;M;off
_remember;modules/;X11;M;off
admin_memory_l1;modules/;X13;M;off
admin_memory_l3;modules/;X15;M;off
class MemoryService;modules/;X16;M;off
memory_l2_embeddings;migrations/;X19;M;off
compile_loop_graph;modules/;X5;A;off
_run_turn_inner;modules/;X17;A;off
from ...chat_model import ToolCallAccumulator;modules/;X5;A;off
graph/nodes.py;runtimes/;X1;A;off
build_session_graph;runtimes/;X1;A;off
InMemoryToolExecutor;runtimes/;X1;A;off
RULES_EOF

if [ "$failed" -ne 0 ]; then
  echo ""
  echo "✗ 旧实现仍有残留 —— 见上面的命中列表（台账：docs/refactor/session-architecture/cleanup-ledger.md）"
  exit 1
fi

echo "✓ 旧实现扫描通过（启用 $enabled 条规则，跳过 $skipped 条尚未启用）"
