"""Admin + catalog agent service."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.agent_runtime.application.catalog_ports import (
    CatalogAgentRepository,
    CatalogAgentUserStateRepository,
)
from qzdap.modules.agent_runtime.domain.catalog import (
    CatalogAgent,
    is_workspace_visible,
)
from qzdap.modules.agent_runtime.domain.catalog_errors import (
    CatalogAgentDisabled,
    CatalogAgentNotFound,
    CatalogCapabilityUnavailable,
)


class AgentCatalogService:
    def __init__(
        self,
        agents: CatalogAgentRepository,
        user_state: CatalogAgentUserStateRepository | None = None,
        evaluator: Any | None = None,
    ) -> None:
        self._agents = agents
        self._user_state = user_state
        self._evaluator = evaluator
        self._tenant_id: UUID | None = None
        self._workspace_id: UUID | None = None

    def bind_scope(self, *, tenant_id: UUID, workspace_id: UUID) -> None:
        self._tenant_id, self._workspace_id = tenant_id, workspace_id

    async def list_admin(
        self,
        *,
        workspace_id: UUID,
        search: str = "",
        tab: str = "all",
        sort_key: str = "updated",
    ) -> list[dict[str, Any]]:
        items = await self._agents.list_for_workspace(workspace_id)
        query = search.strip().lower()
        filtered: list[CatalogAgent] = []
        for agent in items:
            if tab not in ("all", "", None) and agent.status != tab:
                continue
            hay = f"{agent.name} {agent.description} {agent.owner} {agent.category}".lower()
            if query and query not in hay:
                continue
            filtered.append(agent)
        if sort_key == "calls":
            filtered.sort(key=lambda item: item.calls, reverse=True)
        elif sort_key == "name":
            filtered.sort(key=lambda item: item.name)
        elif sort_key == "rating":
            filtered.sort(key=lambda item: item.rating, reverse=True)
        else:
            filtered.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in filtered]

    async def get_admin(self, agent_id: UUID) -> dict[str, Any]:
        return (await self._require(agent_id)).to_admin_dict()

    async def get_published(self, agent_id: UUID) -> CatalogAgent:
        agent = await self._require(agent_id)
        if agent.status not in {"published", "graying"}:
            raise CatalogAgentDisabled(f"agent {agent_id} is {agent.status}")
        return agent

    async def create(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        agent = CatalogAgent.create(
            id=_parse_id(body.get("id")),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名智能体"),
            category=str(body.get("category") or "企业通用"),
            owner=str(body.get("owner") or "管理员"),
            description=str(body.get("description") or ""),
            model=str(body.get("model") or ""),
        )
        agent = agent.apply_patch(body)
        await self._agents.add(agent)
        return agent.to_admin_dict()

    async def update(self, *, agent_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        agent = await self._require(agent_id)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        updated = agent.apply_patch(patch).add_audit("更新智能体")
        await self._agents.update(updated)
        return updated.to_admin_dict()

    async def delete(self, agent_id: UUID) -> dict[str, Any]:
        await self._require(agent_id)
        await self._agents.delete(agent_id)
        return {"ok": True, "id": str(agent_id)}

    async def bulk_delete(self, ids: list[str]) -> dict[str, list[str]]:
        agents = [await self._require(UUID(raw)) for raw in dict.fromkeys(ids)]
        for agent in agents:
            await self._agents.delete(agent.id)
        return {"ids": [str(a.id) for a in agents]}

    async def batch_status(
        self, *, ids: list[str], status: str
    ) -> dict[str, list[str]]:
        from qzdap.modules.agent_runtime.domain.catalog import AGENT_STATUSES

        if status not in AGENT_STATUSES:
            raise ValueError("invalid agent status")
        agents = [await self._require(UUID(raw)) for raw in dict.fromkeys(ids)]
        for agent in agents:
            await self.update(agent_id=agent.id, body={"status": status})
        return {"ids": [str(a.id) for a in agents]}

    async def star(self, agent_id: UUID, starred: bool) -> dict[str, Any]:
        agent = await self._require(agent_id)
        updated = agent.apply_patch({"starred": starred})
        await self._agents.update(updated)
        return updated.to_admin_dict()

    async def versions(self, agent_id: UUID) -> dict[str, Any]:
        agent = await self._require(agent_id)
        return {"agentId": str(agent.id), "versions": list(agent.versions)}

    async def audit(self, agent_id: UUID) -> list[dict[str, Any]]:
        return list((await self._require(agent_id)).audit_events)

    async def rollback(self, *, agent_id: UUID, version: str) -> dict[str, Any]:
        agent = await self._require(agent_id)
        record = next((v for v in agent.versions if v.get("version") == version), None)
        snapshot = record.get("snapshot") if record else None
        if not isinstance(snapshot, dict):
            raise CatalogCapabilityUnavailable("该版本没有可恢复的配置快照")
        restored = (
            agent.apply_patch(snapshot).add_audit("回滚版本", detail=version).publish()
        )
        restored.versions[0]["rollbackOf"] = version
        await self._agents.update(restored)
        return restored.to_admin_dict()

    async def evaluations(self, agent_id: UUID) -> dict[str, Any]:
        agent = await self._require(agent_id)
        runs = [
            event["run"]
            for event in agent.audit_events
            if isinstance(event.get("run"), dict)
        ]
        return {"agentId": str(agent.id), "runs": runs}

    async def run_eval(
        self, agent_id: UUID, *, cases: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        agent = await self._require(agent_id)
        cases = cases or (agent.profile or {}).get("evaluationCases") or []
        if not cases or self._evaluator is None:
            raise CatalogCapabilityUnavailable(
                "智能体基线评测尚未配置执行器或用例，未执行评测"
            )
        validated = []
        for case in cases:
            if not isinstance(case, dict):
                raise TypeError("evaluation case must be object")
            prompt = str(case.get("input") or case.get("prompt") or "").strip()
            expected = str(
                case.get("expected") or case.get("expectedOutput") or ""
            ).strip()
            if not prompt or not expected:
                raise ValueError("each case requires input and expected output")
            validated.append((prompt, expected))
        results = []
        for prompt, expected in validated:
            output = await self._evaluator(agent=agent, prompt=prompt)
            results.append(
                {
                    "input": prompt,
                    "expected": expected,
                    "output": output,
                    "passed": expected in output,
                }
            )
        passed = sum(1 for r in results if r["passed"])
        run = {
            "id": str(uuid4()),
            "name": "基线评测",
            "at": datetime.now(UTC).isoformat(),
            "status": "passed" if passed == len(results) else "failed",
            "caseCount": len(results),
            "passRate": passed / len(results),
            "cases": results,
        }
        updated = agent.add_audit("执行基线评测", detail=f"{passed}/{len(results)}")
        updated.audit_events[-1]["run"] = run
        updated = replace(
            updated,
            evaluation_runs=agent.evaluation_runs + 1,
            evaluation_pass_rate=passed / len(results),
            evaluation_failed_cases=len(results) - passed,
        )
        await self._agents.update(updated)
        return {"agentId": str(agent_id), **run}

    async def diff(
        self, *, agent_id: UUID, left_version: str, right_version: str
    ) -> dict[str, Any]:
        agent = await self._require(agent_id)
        records = {v.get("version"): v for v in agent.versions}
        left, right = records.get(left_version), records.get(right_version)
        if (
            not left
            or not right
            or not isinstance(left.get("snapshot"), dict)
            or not isinstance(right.get("snapshot"), dict)
        ):
            raise CatalogCapabilityUnavailable(
                "尚未存储智能体版本快照，无法比较历史版本"
            )
        changes = {
            key: {
                "before": left["snapshot"].get(key),
                "after": right["snapshot"].get(key),
            }
            for key in set(left["snapshot"]) | set(right["snapshot"])
            if left["snapshot"].get(key) != right["snapshot"].get(key)
        }
        diff_text = "\n".join(
            f"{key}: {json.dumps(change, ensure_ascii=False)}"
            for key, change in changes.items()
        )
        return {
            "agentId": str(agent_id),
            "leftVersion": left_version,
            "rightVersion": right_version,
            "changes": changes,
            "diff": diff_text,
        }

    async def export(
        self, *, workspace_id: UUID, ids: list[str] | None = None
    ) -> dict[str, Any]:
        if self._workspace_id is not None and workspace_id != self._workspace_id:
            raise PermissionError("scope mismatch")
        wanted = set(ids or [])
        rows = [
            a
            for a in await self._agents.list_for_workspace(workspace_id)
            if (not wanted or str(a.id) in wanted)
            and (self._tenant_id is None or a.tenant_id == self._tenant_id)
        ]
        return {"count": len(rows), "agents": [a.to_admin_dict() for a in rows]}

    async def list_catalog(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._agents.list_for_workspace(workspace_id)
        out: list[dict[str, Any]] = []
        for agent in items:
            if agent.status not in {"published", "graying"}:
                continue
            if not is_workspace_visible(list(agent.visible_scope)):
                continue
            out.append(agent.to_catalog_dict())
        return out

    async def set_favorite(
        self, *, agent_id: UUID, user_id: UUID, on: bool
    ) -> dict[str, Any]:
        agent = await self._require(agent_id)
        if self._user_state is not None:
            await self._user_state.set_favorite(
                tenant_id=agent.tenant_id,
                workspace_id=agent.workspace_id,
                user_id=user_id,
                agent_id=agent_id,
                on=on,
            )
        return {**agent.to_catalog_dict(), "id": str(agent_id)}

    async def _require(self, agent_id: UUID) -> CatalogAgent:
        agent = await self._agents.get(agent_id)
        if (
            agent is None
            or (
                self._workspace_id is not None
                and agent.workspace_id != self._workspace_id
            )
            or (self._tenant_id is not None and agent.tenant_id != self._tenant_id)
        ):
            raise CatalogAgentNotFound(f"agent {agent_id} not found")
        return agent


def _parse_id(raw: Any) -> UUID:
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    return uuid4()


__all__ = ["AgentCatalogService"]
