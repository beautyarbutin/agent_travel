"""
地图工具 - 调用高德开放平台 API 获取路线规划
需要配置环境变量: AMAP_API_KEY (Web服务专属Key)
"""
import os
import requests
from dotenv import load_dotenv

# 加载 .env 文件
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, '.env'))

def _get_amap_key():
    key = os.getenv("AMAP_API_KEY")
    if not key:
        raise ValueError("缺少高德地图API密钥。请在 .env 文件中配置 AMAP_API_KEY=你的Web服务Key")
    return key

def _geocode(address: str) -> str:
    """将地址转换为高德坐标 (lng,lat)"""
    key = _get_amap_key()
    url = f"https://restapi.amap.com/v3/geocode/geo?address={address}&key={key}"
    resp = requests.get(url).json()
    
    if resp.get("status") == "1" and resp.get("geocodes"):
        return resp["geocodes"][0]["location"]
    else:
        raise Exception(f"无法解析地址 '{address}' 的坐标: {resp.get('info', '未知错误')}")

def get_driving_route(origin: str, destination: str) -> str:
    """
    获取两个地点之间的真实驾车路线规划、距离和预计耗时。
    
    Args:
        origin: 出发地，如"德州市"或"北京天安门"
        destination: 目的地，如"故城县二道街"
        
    Returns:
        包含距离、耗时和主要路线的文本信息
    """
    try:
        # 1. 地址转坐标
        orig_coord = _geocode(origin)
        dest_coord = _geocode(destination)
        
        # 2. 调用路径规划 API
        key = _get_amap_key()
        url = f"https://restapi.amap.com/v3/direction/driving?origin={orig_coord}&destination={dest_coord}&key={key}&extensions=all"
        resp = requests.get(url).json()
        
        if resp.get("status") != "1":
            return f"查询路线失败: {resp.get('info', '未知错误')}"
            
        route = resp["route"]
        paths = route.get("paths", [])
        
        if not paths:
            return f"没有找到从 {origin} 到 {destination} 的驾车路线。"
            
        # 取第一条推荐路线
        path = paths[0]
        
        # 数据转换 (米 -> 公里，秒 -> 分钟/小时)
        distance = int(path["distance"]) / 1000
        duration_sec = int(path["duration"])
        
        if duration_sec > 3600:
            duration_str = f"{duration_sec // 3600}小时 {duration_sec % 3600 // 60}分钟"
        else:
            duration_str = f"{duration_sec // 60}分钟"
            
        # 提取途径的主要道路 (省道、国道、高速)
        main_roads = set()
        for step in path.get("steps", []):
            road = step.get("road")
            if road and any(keyword in road for keyword in ["省道", "国道", "高速", "S", "G"]):
                main_roads.add(road)
                
        # 过滤掉空的或者未命名的
        main_roads = [r for r in main_roads if r and "无名" not in r]
        
        # 组装返回结果
        result = f"🚗 **驾车路线规划：{origin} ➡️ {destination}**\n\n"
        result += f"- **预计耗时**：约 {duration_str}\n"
        result += f"- **总距离**：约 {distance:.1f} 公里\n"
        
        if main_roads:
            result += f"- **途经主要道路**：{', '.join(main_roads)}\n"
            
        # 提取步骤摘要 (最多显示前5步)
        steps = path.get("steps", [])
        result += "\n**主要行驶步骤摘要：**\n"
        for i, step in enumerate(steps[:5]):
            instruction = step.get("instruction", "").split(",")[0]  # 简化指令
            result += f"{i+1}. {instruction}\n"
            
        if len(steps) > 5:
            result += f"...（完整路线还有 {len(steps)-5} 步）"
            
        return result
        
    except ValueError as ve:
        return f"系统提示: {str(ve)}\n请管理员去高德开放平台申请Web服务Key并在.env中配置，才能使用真实的路线规划功能！"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"查询路线时发生系统错误: {str(e)}\n你可以根据你的内置知识估算一下大概距离和时间。"
