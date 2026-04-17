import logging
import re
from typing import Optional

from openagents.agents.collaborator_agent import CollaboratorAgent
from openagents.agents.orchestrator import orchestrate_agent
from openagents.models.agent_actions import AgentActionType, AgentTrajectory
from openagents.models.event_context import EventContext

logger = logging.getLogger(__name__)


class SpotFallbackAgent(CollaboratorAgent):
    """Spot agent with a narrow fallback for direct-response message loss."""

    _SPOT_TOOL_SUFFIXES = (
        "search_spots",
    )
    _MESSAGE_TOOL_NAMES = {"send_channel_message", "reply_channel_message"}
    _DISABLED_TOOL_NAMES = {
        "mcp_travel_mcp_server_search_local_knowledge",
        "mcp_travel_mcp_server_search_combined",
    }

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
        tools = [tool for tool in tools if self._tool_name(tool) not in self._DISABLED_TOOL_NAMES]

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
        if self._has_message_tool_call(trajectory):
            return

        has_spot_tool_call = self._has_successful_spot_tool_call(trajectory)
        response_text = self._extract_direct_response_text(trajectory)
        if not response_text and not has_spot_tool_call:
            logger.info(
                "[%s] Spot fallback skipped: no successful spot tool call and no direct-response text",
                self.agent_id,
            )
            return
        if not response_text:
            response_text = self._build_spot_summary_from_tool_result(trajectory)
        if not response_text:
            logger.info(
                "[%s] Spot fallback skipped: spot tool call succeeded but no usable fallback text was available",
                self.agent_id,
            )
            return

        messaging_adapter = self._get_messaging_adapter()
        if messaging_adapter is None:
            logger.warning(
                "[%s] Spot fallback skipped: messaging adapter not available",
                self.agent_id,
            )
            return

        await messaging_adapter.send_channel_message(
            channel="general", text=response_text
        )
        logger.info(
            "[%s] Spot fallback sent direct-response content to #general",
            self.agent_id,
        )

    @staticmethod
    def _tool_name(tool) -> str:
        if isinstance(tool, dict):
            if isinstance(tool.get("function"), dict):
                return str(tool["function"].get("name", ""))
            return str(tool.get("name", ""))

        name = getattr(tool, "name", None)
        if name:
            return str(name)

        tool_name = getattr(tool, "tool_name", None)
        if tool_name:
            return str(tool_name)

        function = getattr(tool, "function", None)
        if function is not None:
            function_name = getattr(function, "name", None)
            if function_name:
                return str(function_name)

        return ""

    def _is_router_direct_message(self, context: EventContext) -> bool:
        source_name = self._normalize_source_id(context.incoming_event.source_id)
        event_name = context.incoming_event.event_name or ""
        return source_name == "travel_router" and "direct_message" in event_name

    def _has_successful_spot_tool_call(self, trajectory: AgentTrajectory) -> bool:
        for action in trajectory.actions:
            if action.action_type != AgentActionType.CALL_TOOL:
                continue
            tool_name = str(action.payload.get("tool_name", ""))
            status = action.payload.get("status")
            if status != "success":
                continue
            if tool_name.endswith(self._SPOT_TOOL_SUFFIXES):
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

    def _build_spot_summary_from_tool_result(self, trajectory: AgentTrajectory) -> str:
        for action in reversed(trajectory.actions):
            if action.action_type != AgentActionType.CALL_TOOL:
                continue
            payload = action.payload or {}
            tool_name = str(payload.get("tool_name", ""))
            status = payload.get("status")
            if status != "success":
                continue
            if not tool_name.endswith(self._SPOT_TOOL_SUFFIXES):
                continue

            result = str(payload.get("result", "")).strip()
            if not result:
                continue
            if "错误" in result:
                return "很抱歉，景点检索工具当前返回错误：\n\n" + result
            return "🏛️ 已为您整理到景点/攻略信息：\n\n" + result
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
