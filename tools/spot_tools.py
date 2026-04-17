"""
景点检索工具 - 混合架构 (BM25关键词 + FAISS向量 + 高德API)
包含:
1. 本地 RAG 知识库：BM25 + bge-small-zh FAISS 混合检索
2. 高德地图 POI 搜索 API
"""
import os
import sys
import json
import logging
import requests
import numpy as np
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("faiss").setLevel(logging.WARNING)
logging.getLogger("faiss.loader").setLevel(logging.WARNING)

# 加载 .env
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, '.env'))

# ============================================================
# 全局单例：FAISS 索引 + Embedding 模型 + 结构化文档
# ============================================================
_faiss_index = None
_embed_model = None
_knowledge_docs = None

def _load_rag_engine():
    """懒加载 RAG 引擎（只在第一次调用时加载模型和索引）"""
    global _faiss_index, _embed_model, _knowledge_docs
    
    if _knowledge_docs is not None:
        return  # 已加载过
    
    storage_dir = os.path.join(base_dir, 'storage')
    doc_path = os.path.join(storage_dir, 'doecment.json')
    faiss_path = os.path.join(storage_dir, 'faiss_index.bin')
    
    # 加载结构化文档
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            _knowledge_docs = json.load(f)
        logger.info("加载结构化知识库: %s 个条目", len(_knowledge_docs))
    except Exception as e:
        logger.warning("加载知识库文档失败: %s", e)
        _knowledge_docs = []
        return
    
    # 加载 FAISS 索引和 Embedding 模型
    if os.path.exists(faiss_path):
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
            _faiss_index = faiss.read_index(faiss_path)
            _embed_model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            logger.info("加载 FAISS 索引: %s 个向量", _faiss_index.ntotal)
            logger.info("加载 bge-small-zh-v1.5 Embedding 模型")
        except Exception as e:
            logger.warning("加载 FAISS/Embedding 失败: %s", e)
            logger.warning("将降级为纯关键词检索模式")
    else:
        logger.warning("未找到 FAISS 索引，将使用纯关键词检索模式")
        logger.warning("请先运行: python tools/build_spot_vectors.py")


def _bm25_score(query: str, spot: dict) -> float:
    """BM25 风格的关键词打分"""
    score = 0.0
    # 城市匹配（去掉"市"后缀，如 "杭州市" -> "杭州"）
    city = spot.get('city', '')
    city_core = city.replace("市", "")
    if city_core and len(city_core) >= 2 and city_core in query:
        score += 5.0
    # 区县匹配
    district = spot.get('district', '')
    dist_core = district.replace("区", "").replace("县", "").replace("旗", "")
    if dist_core and len(dist_core) >= 2 and dist_core in query:
        score += 5.0
    # 景点名直接命中（最强信号）
    spot_name = spot.get('spot_name', '')
    if spot_name and spot_name in query:
        score += 15.0
    elif spot_name and len(spot_name) >= 2:
        # 部分匹配（如 query="故宫博物院怎么玩" 匹配 spot_name="故宫博物院"）
        if query in spot_name or any(kw in query for kw in [spot_name[:2], spot_name[:3]] if len(kw) >= 2):
            score += 8.0
    # 标签碰撞
    for tag in spot.get('tags', []):
        if tag in query:
            score += 2.0
    # 内容词频
    content = spot.get('content', '')
    matched = sum(1 for ch in query if ch in content)
    score += float(matched / max(len(query), 1)) * 2.0
    return score


def search_knowledge(query: str) -> str:
    """
    搜索本地景点深度游玩指南（RAG 知识库）。
    使用 BM25 关键词 + FAISS 向量语义的混合检索技术。
    """
    try:
        _load_rag_engine()
        
        if not _knowledge_docs:
            return "抱歉，景点知识库尚未建立，无法检索。"
        
        logger.info("[Hybrid RAG] 检索: %s", query)
        
        n = len(_knowledge_docs)
        # 综合得分数组（每条文档一个分）
        final_scores = np.zeros(n, dtype=np.float32)
        
        # ---- 路线1: FAISS 向量语义检索 ----
        if _faiss_index is not None and _embed_model is not None:
            q_vec = _embed_model.encode(
                [query],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            q_vec = np.array(q_vec, dtype=np.float32)
            scores, indices = _faiss_index.search(q_vec, min(n, 5))
            for rank, (idx, score) in enumerate(zip(indices[0], scores[0])):
                if idx >= 0 and idx < n:
                    # 向量相似度得分 * 权重
                    final_scores[idx] += score * 5.0
            logger.info("向量检索完成 (FAISS top-5)")
        else:
            logger.warning("向量检索不可用，仅使用关键词")
        
        # ---- 路线2: BM25 关键词检索 ----
        for i, spot in enumerate(_knowledge_docs):
            bm25 = _bm25_score(query, spot)
            
            # 给独家手写攻略加特权分，但只在有关键词匹配时才加
            # 避免搜"故宫"时手写的"庆林寺塔"挤掉真正的故宫
            if spot.get('source') == '独家手写攻略' and bm25 > 0:
                bm25 += 50.0
                
            final_scores[i] += bm25
        logger.info("关键词检索完成 (BM25)")
        
        # ---- 合并排序，取 Top-5 ----
        top_indices = final_scores.argsort()[::-1][:5]
        top_results = []
        for idx in top_indices:
            if final_scores[idx] > 0.5:  # 最低及格线
                top_results.append((float(final_scores[idx]), _knowledge_docs[idx]))
        
        if not top_results:
            return f"知识库中未找到与 '{query}' 高度相关的指南。"
        
        # ---- 格式化输出（带引用来源） ----
        formatted = []
        for i, (score, spot) in enumerate(top_results):
            tags_str = ", ".join(spot.get('tags', []))
            header = (
                f"🔖 【独家指南 {i+1}】 {spot.get('city','')} {spot.get('district','')}: "
                f"{spot.get('spot_name','')} "
                f"(游玩需:{spot.get('duration','未知')} | 消费:{spot.get('budget','未知')} | "
                f"相关度:{score:.1f}分)\n"
                f"🏷️ 标签: {tags_str}\n"
                f"📋 来源ID: {spot.get('id','')}"
            )
            formatted.append(f"{header}\n{spot.get('content', '')}")
        
        result = "\n\n".join(formatted)
        return (
            f"💡 在深度知识库中找到以下关于 '{query}' 的独家建议：\n\n"
            f"{result}\n\n"
            f"请结合以上带标签、时长和预算的知识，为用户提供有深度的推荐。"
        )
        
    except Exception as e:
        import traceback
        logger.exception("检索知识库时发生错误")
        return f"检索知识库时发生错误: {str(e)}"


# ============================================================
# 高德地图 POI 景点搜索
# ============================================================
def search_spots(query: str) -> str:
    """
    搜索指定城市或地区的景点信息。使用高德地图 POI 搜索 API。

    Args:
        query: 查询词，例如"庆云县景点"、"故城县有什么好玩的"
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return "错误：未配置 AMAP_API_KEY，无法搜索景点。"

    try:
        url = "https://restapi.amap.com/v3/place/text"
        params = {
            "key": api_key,
            "keywords": query,
            "types": "110000",
            "city": "",
            "citylimit": "false",
            "offset": 10,
            "output": "json",
            "extensions": "all",
        }

        for suffix in ["县", "市", "区", "镇", "州"]:
            if suffix in query:
                params["city"] = query
                params["keywords"] = "景点 旅游 风景"
                break

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") != "1":
            return f"高德 API 请求失败: {data.get('info', '未知错误')}"

        pois = data.get("pois", [])
        if not pois:
            params["types"] = ""
            params["keywords"] = query + " 景点 旅游"
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            pois = data.get("pois", [])

        if not pois:
            return f"没有找到关于 '{query}' 的景点信息。"

        results = []
        for i, poi in enumerate(pois, 1):
            name = poi.get("name", "未知")
            address = poi.get("address", "暂无地址")
            pname = poi.get("pname", "")
            cityname = poi.get("cityname", "")
            adname = poi.get("adname", "")
            location_str = " > ".join([p for p in [pname, cityname, adname] if p])
            entry = f"{i}. 📍 {name}\n   📌 位置：{location_str}\n   🏠 地址：{address}"
            tel = poi.get("tel", "")
            if tel and tel != "[]":
                entry += f"\n   📞 {tel}"
            results.append(entry)

        total = data.get("count", len(pois))
        return f"'{query}' 相关景点（共{total}个，展示{len(pois)}个）：\n\n" + "\n\n".join(results)

    except Exception as e:
        return f"搜索景点时发生错误: {str(e)}"


# ============================================================
# 融合检索：RAG 本地知识库 + 高德 POI 实时数据
# ============================================================
def search_combined(query: str) -> str:
    """
    融合检索：同时查询本地 RAG 知识库（FAISS+BM25）和高德地图 POI API，
    以"深度攻略 + 实时信息"两层结构呈现结果。

    策略：
    - 本地 RAG：提供独家攻略、避坑指南、特色美食、预算等深度内容
    - 高德 POI：提供权威地址、电话、实时评分等实时数据
    - 高德查到的 POI 名称反向增强 BM25 打分，实现跨来源互补

    Args:
        query: 用户问题，例如 "衡水湖怎么玩" 或 "故城县有什么景点"
    """
    sections = []

    # ---- Part 1: RAG 本地知识库（深度攻略） ----
    try:
        rag_result = search_knowledge(query)
        if rag_result and "未找到" not in rag_result and "错误" not in rag_result:
            sections.append(
                "📚【本地深度攻略（RAG 知识库）】\n"
                "（来源：独家手写攻略 + 结构化知识库，含游玩时长/预算/避坑等）\n\n"
                + rag_result
            )
    except Exception as e:
        sections.append(f"⚠️ RAG 检索异常: {e}")

    # ---- Part 2: 高德 POI 实时数据 ----
    amap_section = ""
    raw_poi_names = []     # 收集高德返回的景点名，用于回注增强
    api_key = os.getenv("AMAP_API_KEY")

    if not api_key:
        sections.append("⚠️ 未配置 AMAP_API_KEY，跳过实时景点数据。")
    else:
        try:
            url = "https://restapi.amap.com/v3/place/text"
            params = {
                "key": api_key,
                "keywords": query,
                "types": "110000",
                "city": "",
                "citylimit": "false",
                "offset": 5,      # 融合模式下取 5 条即可，避免信息过载
                "output": "json",
                "extensions": "all",
            }
            for suffix in ["县", "市", "区", "镇", "州"]:
                if suffix in query:
                    params["city"] = query
                    params["keywords"] = "景点 旅游 风景"
                    break

            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            if data.get("status") == "1":
                pois = data.get("pois", [])
                if not pois:
                    params["types"] = ""
                    params["keywords"] = query + " 景点 旅游"
                    resp = requests.get(url, params=params, timeout=10)
                    data = resp.json()
                    pois = data.get("pois", [])

                if pois:
                    poi_lines = []
                    for i, poi in enumerate(pois, 1):
                        name = poi.get("name", "未知")
                        raw_poi_names.append(name)
                        pname = poi.get("pname", "")
                        cityname = poi.get("cityname", "")
                        adname = poi.get("adname", "")
                        address = poi.get("address", "暂无")
                        loc_str = " > ".join(p for p in [pname, cityname, adname] if p)
                        rating = poi.get("biz_ext", {}).get("rating", "")
                        cost = poi.get("biz_ext", {}).get("cost", "")

                        line = (
                            f"{i}. 📍 **{name}**\n"
                            f"   📌 {loc_str}\n"
                            f"   🏠 {address}"
                        )
                        if rating:
                            line += f"\n   ⭐ 评分：{rating}"
                        if cost:
                            line += f"\n   💰 人均：¥{cost}"
                        tel = poi.get("tel", "")
                        if tel and tel != "[]":
                            line += f"\n   📞 {tel}"
                        poi_lines.append(line)

                    amap_section = (
                        "🗺️【实时景点数据（高德地图 POI API）】\n"
                        "（来源：高德地图，数据实时，含地址/评分/电话）\n\n"
                        + "\n\n".join(poi_lines)
                    )
                    sections.append(amap_section)
                else:
                    sections.append(f"🗺️ 高德地图未找到 '{query}' 相关景点。")
            else:
                sections.append(f"🗺️ 高德 API 请求失败: {data.get('info', '未知')}")

        except Exception as e:
            sections.append(f"⚠️ 高德 POI 检索异常: {e}")

    # ---- Part 3: 跨来源互补提示 ----
    # 若高德返回了景点名，检查是否在 RAG 里有对应攻略
    complement_tips = []
    if raw_poi_names and _knowledge_docs:
        for poi_name in raw_poi_names[:3]:  # 只取前 3 个
            matched = any(
                poi_name in (d.get("spot_name", "") + d.get("content", ""))
                for d in _knowledge_docs
            )
            if not matched and len(poi_name) >= 2:
                complement_tips.append(f"  • 「{poi_name}」暂无本地深度攻略，建议参考高德实时信息。")

    if complement_tips:
        sections.append(
            "💡【来源互补说明】\n"
            "以下景点在本地知识库中暂无深度攻略，" 
            "实时数据来自高德地图：\n" + "\n".join(complement_tips)
        )

    if not sections:
        return f"抱歉，未能找到关于 '{query}' 的任何信息，请尝试更换关键词。"

    return (
        f"🔍 关于「{query}」的综合检索结果\n"
        f"{'=' * 40}\n\n"
        + "\n\n" + "─" * 40 + "\n\n".join(sections)
    )
