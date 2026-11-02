"""真实模型后端（OpenAI 兼容端点，零依赖，用 urllib）。

用法：
    export DEEPSEEK_API_KEY=sk-...
    python3 demo_dual_agent.py --llm           # actor/verifier/revisor 都走真模型
    python3 demo_dual_agent.py --llm --strict

可选：
    LLM_BASE_URL  默认 https://api.deepseek.com/v1（任何 OpenAI 兼容端点都行）
    LLM_MODEL     默认 deepseek-chat
    TAVILY_API_KEY 设置后 verifier 用 Tavily 搜真证据；不设则退回 mock 证据库
"""

import json
import os
import urllib.request

BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


def available():
    return bool(API_KEY)


def _post_json(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def chat(messages, max_tokens=800, temperature=0.7):
    if not API_KEY:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY / LLM_API_KEY，无法使用真实模型")
    data = _post_json(
        BASE_URL.rstrip("/") + "/chat/completions",
        {
            "model": MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        {"Authorization": "Bearer " + API_KEY},
    )
    return data["choices"][0]["message"]["content"].strip()


def llm_draft(question):
    return chat(
        [
            {
                "role": "system",
                "content": (
                    "你是给出建议的助手。直接给建议，口吻可以笃定一点"
                    "（这是为了测试验证器的场景），可以自然地写一些引用。"
                ),
            },
            {"role": "user", "content": question},
        ]
    )


def llm_revise(text, verdicts):
    lines = [f"- {v.status}: {v.claim.text}（{v.note}）" for v in verdicts]
    return chat(
        [
            {
                "role": "system",
                "content": (
                    "你是修订员。按核查结论改写草稿：删掉没有出处的引用或降级为推测，"
                    "事实错误改对，绝对化措辞软化，建议补一两个替代方案。只输出修订后的正文。"
                ),
            },
            {
                "role": "user",
                "content": "草稿：\n" + text + "\n\n核查结论：\n" + ("\n".join(lines) or "（无）"),
            },
        ]
    )


def search(claim_text, max_results=2):
    """用 Tavily 搜证据；未配置 key 时返回 None（调用方退回 mock）。

    证据统一格式：{status, tier, confidence, url, snippet, published_at}
    """
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return None
    data = _post_json(
        "https://api.tavily.com/search",
        {
            "api_key": key,
            "query": claim_text,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        },
        {},
    )
    results = data.get("results") or []
    if not results:
        return {
            "status": "unsupported",
            "tier": "联网",
            "note": "联网检索无结果",
            "confidence": 0.35,
            "url": "",
            "snippet": "",
            "published_at": "",
        }
    top = results[0]
    snippet = (top.get("content") or "")[:200].replace("\n", " ").strip()
    published = top.get("published_date") or top.get("published_at") or ""
    return {
        "status": "supported",
        "tier": "联网",
        "note": f"{top.get('title', '')} | {top.get('url', '')}",
        "confidence": 0.85,
        "url": top.get("url", ""),
        "snippet": snippet,
        "published_at": published,
    }


def llm_verify_claim(claim_text, cfg=None):
    """单条断言核查（评测用）：返回 {status, confidence, evidence_url, snippet}。"""
    prompt = (
        "你是核查员。判断下面这条断言：\n"
        f"「{claim_text}」\n"
        "输出 JSON：{"
        '"status": "supported|unsupported|refuted", '
        '"confidence": 0-1, '
        '"evidence_url": "能给就给出处 URL，否则空串", '
        '"snippet": "一句原文依据"'
        "}\n只输出 JSON。"
    )
    out = chat([{"role": "user", "content": prompt}], max_tokens=300, temperature=0)
    start, end = out.find("{"), out.rfind("}")
    data = json.loads(out[start : end + 1])
    status = str(data.get("status", "unsupported")).strip().lower()
    if status not in ("supported", "unsupported", "refuted"):
        status = "unsupported"
    try:
        conf = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    return {
        "status": status,
        "confidence": max(0.0, min(1.0, conf)),
        "evidence_url": str(data.get("evidence_url") or ""),
        "snippet": str(data.get("snippet") or ""),
    }
