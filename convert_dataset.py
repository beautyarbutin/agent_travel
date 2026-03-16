"""
训练数据格式转换脚本
将 function_call/observation 格式转换为 gpt+tool_calls 格式
使其兼容 LLaMA-Factory → GGUF → LM Studio 的 tool calling 推理链路
"""
import json
import copy

INPUT_FILE = r"d:\20251224\AI_Study\OpenAgents\openagents_sft_dataset.json"
OUTPUT_FILE = r"d:\20251224\AI_Study\OpenAgents\openagents_tool_calling_v2.json"

data = json.load(open(INPUT_FILE, "r", encoding="utf-8"))
print(f"原始数据: {len(data)} 条")

converted = []
for sample in data:
    new_sample = {
        "system": sample.get("system", ""),
        "tools": sample.get("tools", ""),
        "conversations": []
    }

    convs = sample["conversations"]
    i = 0
    while i < len(convs):
        msg = convs[i]

        if msg["from"] == "human":
            new_sample["conversations"].append({
                "from": "human",
                "value": msg["value"]
            })
            i += 1

        elif msg["from"] == "function_call":
            # 收集连续的 function_call（可能有多个连续的 tool call）
            tool_calls = []
            fc_data = json.loads(msg["value"])
            tool_calls.append(fc_data)

            # gpt 消息带 tool_calls
            new_sample["conversations"].append({
                "from": "gpt",
                "value": "",
                "tool_calls": tool_calls
            })
            i += 1

            # 下一个应该是 observation
            if i < len(convs) and convs[i]["from"] == "observation":
                new_sample["conversations"].append({
                    "from": "observation",
                    "value": convs[i]["value"]
                })
                i += 1

        elif msg["from"] == "observation":
            # 不应该出现在 function_call 之外，但保留以防万一
            new_sample["conversations"].append({
                "from": "observation",
                "value": msg["value"]
            })
            i += 1
        else:
            i += 1

    converted.append(new_sample)

# 保存
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(converted, f, ensure_ascii=False, indent=2)

print(f"转换完成: {len(converted)} 条")
print(f"输出文件: {OUTPUT_FILE}")

# 预览第一条
print("\n=== 转换后样本 0 预览 ===")
conv0 = converted[0]["conversations"]
for j, m in enumerate(conv0):
    tc = m.get("tool_calls", "")
    tc_str = f" tool_calls={json.dumps(tc, ensure_ascii=False)}" if tc else ""
    val = m["value"][:80]
    print(f"  [{j}] {m['from']}: {val}{tc_str}")
