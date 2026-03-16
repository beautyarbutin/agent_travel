"""
记忆工具 MCP Server
只包含上下文读写的工具，专门给 Router 使用，防止其调用具体业务工具
"""
import os
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载环境变量
base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, '.env'))

mcp = FastMCP("MemoryMCP")

@mcp.tool()
def save_context(
    current_city: str = "",
    origin_city: str = "",
    destination_city: str = "",
    current_spot: str = "",
    travel_party: str = "",
    preferences: str = "",
    departure_time: str = "",
    trip_days: str = "",
    notes: str = "",
) -> str:
    """
    保存/更新用户对话上下文到本地记忆文件（增量更新，只覆盖非空字段）。
    当用户提到城市、景点、跨城出发地/目的地、出行人员、偏好等关键信息时，调用此工具保存。
    """
    try:
        sys.path.insert(0, os.path.join(base_dir, 'tools'))
        from memory_tools import save_context as _save
        return _save(
            current_city=current_city,
            origin_city=origin_city,
            destination_city=destination_city,
            current_spot=current_spot,
            travel_party=travel_party,
            preferences=preferences,
            departure_time=departure_time,
            trip_days=trip_days,
            notes=notes,
        )
    except Exception as e:
        return f"保存上下文时发生错误：{str(e)}"

@mcp.tool()
def get_context() -> str:
    """
    读取当前对话上下文记忆，获取用户之前对话中提到的城市、景点、出行偏好等信息。
    在处理用户请求之前调用此工具，可以了解对话背景。
    """
    try:
        sys.path.insert(0, os.path.join(base_dir, 'tools'))
        from memory_tools import get_context as _get
        return _get()
    except Exception as e:
        return f"读取上下文时发生错误：{str(e)}"

if __name__ == "__main__":
    sys.stderr.write("🚀 Memory MCP Server 启动中...\n")
    mcp.run()
