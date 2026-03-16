import gradio as gr
import time

# 定义界面的主题风格，截图用的就是这种柔和的色调（Teal: 蓝绿色系）
custom_theme = gr.themes.Soft(
    primary_hue="teal",      # 主色调为蓝绿
    neutral_hue="slate",     # 中性色为冷灰亮色
).set(
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_400",
)

def respond(message, chat_history, search_mode, top_k):
    """处理用户消息的伪代码函数"""
    if not message:
        return "", chat_history
        
    # 模拟包含内部 debug 信息的结构化返回（也就是截图气泡下方的浅色小字区域）
    debug_info = (
        "\n\n---\n"
        "<span style='color:gray; font-size:12px'>"
        f"session=session-0e43845b-04d3-4cfc-904c-90e50576ff15<br>"
        f"mode={search_mode}, confidence=0.89<br>"
        f"skill=0, vector=8, rerank={top_k}<br>"
        f"window=4, summaries=1, long_term=0<br>"
        "citations: AI Knowledge/生成式人工智能服务合规备案指南（2026年）.pdf @ p.7 | AI Knowledge/人工智能安全治理研究报告（2025年）.pdf @ p.26"
        "</span>"
    )
    
    # 这里接入你的 OpenAgents 或 RAG 系统
    # 我们这里做一个简单的回显加上假装的思考时间
    time.sleep(1)
    
    bot_message = f"这是模拟大模型的回复内容。我收到了你的问题：**{message}**。\n\n根据系统检索，生成式人工智能服务备案办理流程包括向网信办报备、现场测评、准备技术法务等团队协作材料等步骤。{debug_info}"
    
    chat_history.append((message, bot_message))
    return "", chat_history

def clear_chat():
    return []

# 构建界面布局
with gr.Blocks(title="RAG Chat Console") as demo:
    with gr.Row():
        
        # ========== 左侧控制面板 ==========
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("## RAG Chat Console\n<span style='color:gray; font-size:14px'>Skill 定位 + 向量补召回 + LangGraph 编排</span>")
            
            gr.Markdown("---")
            
            search_mode = gr.Dropdown(
                choices=["hybrid (默认)", "vector_only", "keyword_only"], 
                value="hybrid (默认)", 
                label="检索模式"
            )
            
            top_k = gr.Slider(minimum=1, maximum=20, value=8, step=1, label="Top K: 8")
            
            with gr.Row():
                btn_reindex = gr.Button("重建索引", variant="primary", size="sm")
                btn_new = gr.Button("新会话", variant="primary", size="sm")
                btn_clear = gr.Button("清空窗口", variant="stop", size="sm")
                
            # 状态展示区
            gr.HTML(
                """
                <div style='background-color: white; padding: 15px; border-radius: 8px; border: 1px solid #e5e7eb; font-size: 13px; color: #4b5563; margin-top: 20px; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);'>
                <p style='margin: 0; padding-bottom: 5px;'>状态: ok</p>
                <p style='margin: 0; padding-bottom: 5px;'>chat: lmstudio/qwen3.5-4b</p>
                <p style='margin: 0; padding-bottom: 5px;'>embed: bailian/text-embedding-v4</p>
                <p style='margin: 0; padding-bottom: 5px;'>rerank: bailian/qwen3-rerank</p>
                <p style='margin: 0; padding-bottom: 5px;'>chunks: 1840</p>
                <p style='margin: 0; padding-bottom: 5px;'>vector_dim: 1536</p>
                <p style='margin: 0; padding-bottom: 5px;'>actor: actor-9ec40956-0ec2-4a71-bce9-4ea87debf1fa</p>
                <p style='margin: 0; padding-bottom: 5px; word-break: break-all;'>session: session-0e43845b-04d3-4cfc-904c-90e50576ff15</p>
                </div>
                """
            )
            
        # ========== 右侧主聊天区 ==========
        with gr.Column(scale=3):
            with gr.Row():
                gr.Markdown("### 聊天窗口")
                gr.Markdown("<div style='text-align: right; color: gray; font-size: 12px; margin-top: 10px;'>回车发送，Shift+回车换行</div>")
                
            chatbot = gr.Chatbot(
                height=650, 
                show_label=False,
                avatar_images=(None, "🤖"), # 用户头像是空的，机器人带有头像
                layout="bubble"
            )
            
            with gr.Row(equal_height=True):
                msg = gr.Textbox(
                    placeholder="输入你的问题，例如：2026年AI Agent技术有哪些关键趋势？",
                    show_label=False,
                    container=False, # 隐藏外部容器框使其更加扁平
                    scale=9,
                    lines=2
                )
                btn_send = gr.Button("发送", variant="primary", scale=1)

    # 绑定事件
    msg.submit(respond, inputs=[msg, chatbot, search_mode, top_k], outputs=[msg, chatbot])
    btn_send.click(respond, inputs=[msg, chatbot, search_mode, top_k], outputs=[msg, chatbot])
    btn_clear.click(clear_chat, outputs=[chatbot], queue=False)
    btn_new.click(clear_chat, outputs=[chatbot], queue=False)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, theme=custom_theme, css=".gradio-container {background-color: #f3f4f6;}")
