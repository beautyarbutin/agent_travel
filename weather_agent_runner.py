import logging
import re
from typing import Optional

from openagents.agents.collaborator_agent import CollaboratorAgent
from openagents.agents.orchestrator import orchestrate_agent
from openagents.models.agent_actions import AgentActionType, AgentTrajectory
from openagents.models.event_context import EventContext

logger = logging.getLogger(__name__)


class WeatherFallbackAgent(CollaboratorAgent):
    """Weather agent with fallback delivery when the model forgets to send a channel reply."""

    _WEATHER_TOOL_SUFFIXES = ("get_weather", "get_weather_forecast")
    _MESSAGE_TOOL_NAMES = {"send_channel_message", "reply_channel_message"}

    async def run_agent(
        self,
        context: EventContext,
        instruction: Optional[str] = None,
        max_iterations: Optional[int] = None,
        disable_mcp: Optional[bool] = False,
        disable_mods: Optional[bool] = False,
    ) -> AgentTrajectory:
        tools = []
        if not disable_mcp:
            tools.extend(self._mcp_tools)
        if not disable_mods:
            tools.extend(self._mod_tools)
        tools.extend(self._custom_tools)

        trajectory = await orchestrate_agent(
            context=context,
            agent_config=self.agent_config,
            tools=tools,
            user_instruction=instruction,
            max_iterations=max_iterations,
            disable_finish_tool=True,
            agent_id=self._agent_id,
            agent_client=self._network_client,
        )
        await self._maybe_send_fallback_message(context, trajectory)
        return trajectory

    async def _maybe_send_fallback_message(
        self, context: EventContext, trajectory: AgentTrajectory
    ) -> None:
        if not self._is_router_direct_message(context):
            return
        if not self._has_successful_weather_tool_call(trajectory):
            return
        if self._has_message_tool_call(trajectory):
            return

        response_text = self._extract_direct_response_text(trajectory)
        if not response_text:
            response_text = self._build_weather_summary_from_tool_result(trajectory)
        if not response_text:
            return

        messaging_adapter = self._get_messaging_adapter()
        if messaging_adapter is None:
            logger.warning(
                "[%s] Weather fallback skipped: messaging adapter not available",
                self.agent_id,
            )
            return

        await messaging_adapter.send_channel_message(
            channel="general", text=response_text
        )
        logger.info(
            "[%s] Weather fallback sent response to #general",
            self.agent_id,
        )

    def _is_router_direct_message(self, context: EventContext) -> bool:
        source_name = self._normalize_source_id(context.incoming_event.source_id)
        event_name = context.incoming_event.event_name or ""
        return source_name == "travel_router" and "direct_message" in event_name

    def _has_successful_weather_tool_call(self, trajectory: AgentTrajectory) -> bool:
        for action in trajectory.actions:
            if action.action_type != AgentActionType.CALL_TOOL:
                continue
            tool_name = str(action.payload.get("tool_name", ""))
            status = action.payload.get("status")
            if status != "success":
                continue
            if tool_name.endswith(self._WEATHER_TOOL_SUFFIXES):
                return True
        return False

    def _has_message_tool_call(self, trajectory: AgentTrajectory) -> bool:
        for action in trajectory.actions:
            if action.action_type != AgentActionType.CALL_TOOL:
                continue
            tool_name = str(action.payload.get("tool_name", ""))
            if tool_name in self._MESSAGE_TOOL_NAMES:
                return True
        return False

    def _extract_direct_response_text(self, trajectory: AgentTrajectory) -> str:
        for action in reversed(trajectory.actions):
            if action.action_type != AgentActionType.COMPLETE:
                continue
            payload = action.payload or {}
            if payload.get("reason") != "Agent provided direct response":
                continue
            response_text = str(payload.get("response", "")).strip()
            cleaned = self._strip_think_blocks(response_text)
            if cleaned:
                return cleaned
        return ""

    def _build_weather_summary_from_tool_result(self, trajectory: AgentTrajectory) -> str:
        for action in reversed(trajectory.actions):
            if action.action_type != AgentActionType.CALL_TOOL:
                continue
            tool_name = str(action.payload.get("tool_name", ""))
            if not tool_name.endswith(self._WEATHER_TOOL_SUFFIXES):
                continue
            result = str(action.payload.get("result", "")).strip()
            if not result:
                continue
            if "错误" in result:
                return "很抱歉，天气工具当前返回错误：\n\n" + result
            return "🌤️ 已为您查询到天气信息：\n\n" + result
        return ""

    def _get_messaging_adapter(self):
        adapter = self.get_mod_adapter("messaging")
        if adapter is not None and hasattr(adapter, "send_channel_message"):
            return adapter

        for candidate in self.client.mod_adapters.values():
            if hasattr(candidate, "send_channel_message"):
                return candidate
        return None

    @staticmethod
    def _normalize_source_id(source_id: Optional[str]) -> str:
        if not source_id:
            return ""
        if ":" in source_id:
            return source_id.split(":", 1)[1]
        return source_id

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
        return text.strip()
