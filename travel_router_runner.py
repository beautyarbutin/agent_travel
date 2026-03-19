import logging
from typing import Optional

from openagents.agents.collaborator_agent import CollaboratorAgent
from openagents.agents.orchestrator import orchestrate_agent
from openagents.models.agent_actions import AgentTrajectory
from openagents.models.event_context import EventContext

logger = logging.getLogger(__name__)


class TravelRouterAgent(CollaboratorAgent):
    """Router runner that disables the built-in finish tool for safer handoff."""

    _IGNORED_AGENT_SOURCES = {
        "travel_router",
        "weather_agent",
        "spot_agent",
        "plan_agent",
    }

    async def run_agent(
        self,
        context: EventContext,
        instruction: Optional[str] = None,
        max_iterations: Optional[int] = None,
        disable_mcp: Optional[bool] = False,
        disable_mods: Optional[bool] = False,
    ) -> AgentTrajectory:
        source_id = self._normalize_source_id(context.incoming_event.source_id)
        if source_id in self._IGNORED_AGENT_SOURCES:
            logger.info(
                "[%s] Ignoring message from peer agent source=%s event=%s",
                self.agent_id,
                source_id,
                context.incoming_event.event_name,
            )
            return AgentTrajectory(
                actions=[],
                summary=f"Ignored peer-agent message from {source_id}",
            )

        tools = []
        if not disable_mcp:
            tools.extend(self._mcp_tools)
        if not disable_mods:
            tools.extend(self._mod_tools)
        tools.extend(self._custom_tools)

        return await orchestrate_agent(
            context=context,
            agent_config=self.agent_config,
            tools=tools,
            user_instruction=instruction,
            max_iterations=max_iterations,
            disable_finish_tool=True,
            agent_id=self._agent_id,
            agent_client=self._network_client,
        )

    @staticmethod
    def _normalize_source_id(source_id: Optional[str]) -> str:
        if not source_id:
            return ""
        if ":" in source_id:
            return source_id.split(":", 1)[1]
        return source_id
