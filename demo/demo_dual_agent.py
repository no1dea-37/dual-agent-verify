#!/usr/bin/env python3
"""双 agent 验证管线（actor + verifier）最小可跑原型。

无外部依赖、无网络：证据用内置 mock 库，先看清控制流；
接真实 LLM / DSH 子 agent 时，只需替换 draft() 与 Verifier.lookup() 两处。

用法：
    python3 demo_dual_agent.py           # 用默认参数跑
    python3 demo_dual_agent.py --strict  # 严格模式
    python3 demo_dual_agent.py --off     # 关闭验证，看单 agent 输出
"""

import re
import sys
from dataclasses import dataclass


# ---------------- 配置 ----------------
@dataclass
class Config:
    verify_frequency: str = "risky"      # all | risky | off
    confidence_threshold: float = 0.60   # 低于此值的断言视为「待确认」
    max_searches_per_claim: int = 2
    delay_budget_ms: int = 800           # 流式场景下允许的缓冲时间
    strictness: int = 2                  # 1 宽松 / 2 标准 / 3 严格


# ---------------- mock 证据库 ----------------
# 结构：关键词 -> (来源层级, 状态, 备注)
EVIDENCE = {
    "王教授": ("机构", "unsupported", "没有可引用的原话（回信里没有明确承诺）"),
    "托福": ("官方", "supported", "成绩有效期为两年"),
    "期中": ("官方", "supported", "示例：六场考试安排在同一周"),
}


@dataclass
class Claim:
    text: str
    kind: str    # fact / citation / advice
    risk: int    # 0..3


def extract_claims(text):
    """monitor：把草稿拆成断言，按类型和风险分级。"""
    out = []
    for sent in re.split(r"[。！？\n]", text):
        sent = sent.strip()
        if not sent:
            continue
        if re.search(r"(说过|承诺|答应|留了|原话)", sent):
            out.append(Claim(sent, "citation", 3))
        elif re.search(r"(建议|应该|最好|可以考虑|别急着)", sent):
            out.append(Claim(sent, "advice", 2))
        elif re.search(r"\d", sent):
            out.append(Claim(sent, "fact", 1))
    return out


# ---------------- actor（mock 草稿） ----------------
def draft(question):
    return (
        "你可以现在就发第二封邮件。"
        "王教授在回信里说过，会在学期中给你留一个位置，所以不用等成绩。"
        "建议直接写明「我想进实验室」，态度硬一点。"
        "这样一定能打动他。"
    )


@dataclass
class Verdict:
    claim: Claim
    status: str        # supported / unsupported / refuted
    tier: str
    note: str
    confidence: float


class Verifier:
    def __init__(self, cfg, backend=None):
        self.cfg = cfg
        self.backend = backend
        self.searches = 0

    def lookup(self, claim):
        self.searches += 1
        if self.backend is not None:
            hit = self.backend.search(claim.text)
            if hit:
                return Verdict(claim, hit["status"], hit["tier"], hit["note"], hit["confidence"])
        for key, (tier, status, note) in EVIDENCE.items():
            if key in claim.text:
                conf = 0.90 if status == "supported" else 0.70
                return Verdict(claim, status, tier, note, conf)
        return Verdict(claim, "unsupported", "无", "查不到可引用出处", 0.35)

    def run(self, claims):
        if self.cfg.verify_frequency == "off":
            return []
        results = []
        for c in claims:
            if c.kind == "advice":          # 建议走 rubric，不搜证据
                continue
            risky = c.risk >= 2
            if self.cfg.verify_frequency == "risky" and not risky:
                continue
            results.append(self.lookup(c))
            if self.searches >= self.cfg.max_searches_per_claim * max(1, len(claims)):
                break
        return results


def advice_rubric(text):
    """建议层：只打分，不判对错。"""
    return {
        "替代方案": bool(re.search(r"(或者|也可以|另一个|两条路|选择)", text)),
        "前提假设": bool(re.search(r"(如果|若|前提|假设|在.{0,6}情况下)", text)),
        "信息充分性": bool(re.search(r"(据|资料|目前|已知|不确定|还不了解)", text)),
        "确定性匹配": not re.search(r"(一定|必然|肯定|绝对)", text),
        "边界": not re.search(r"(我替你决定|你必须|只能)", text),
        "利益": not re.search(r"(为了让他|讨好他)", text),
    }


def revise(text, verdicts, cfg):
    """修订：删掉无出处引用、软化绝对化措辞。"""
    if cfg.verify_frequency == "off":
        return text
    body = text
    for v in verdicts:
        if v.status == "unsupported" and v.claim.kind == "citation":
            body = body.replace(v.claim.text + "。", "")
            body = body.replace(v.claim.text, "")
    body = body.replace("一定能打动他。", "大概率会有回音，但不保证。")
    body = body.replace("态度硬一点。", "把措辞放平，说明研究兴趣。")
    return body


def main():
    cfg = Config()
    if "--strict" in sys.argv:
        cfg.strictness = 3
        cfg.verify_frequency = "all"
    if "--off" in sys.argv:
        cfg.verify_frequency = "off"

    backend = None
    if "--llm" in sys.argv:
        try:
            import real_backend
        except ImportError:
            print("找不到 real_backend.py（应和本文件同目录）")
            return
        if not real_backend.available():
            print("未设置 DEEPSEEK_API_KEY / LLM_API_KEY，--llm 需要真实模型 key")
            return
        backend = real_backend

    question = "第二封邮件该不该现在就发？"
    original = backend.llm_draft(question) if backend else draft(question)
    claims = extract_claims(original)
    verdicts = Verifier(cfg, backend).run(claims)

    print("=" * 64)
    print("问题：", question)
    print(f"参数：verify_frequency={cfg.verify_frequency} "
          f"strictness={cfg.strictness} delay_budget={cfg.delay_budget_ms}ms")
    print("\n[actor 草稿]\n", original)

    print(f"\n[monitor 抽取断言] {len(claims)} 条")
    for c in claims:
        print(f"  - [{c.kind} risk={c.risk}] {c.text}")

    print("\n[verifier 结论]")
    if not verdicts:
        print("  （未验证：verify_frequency=off 或不含高风险断言）")
    for v in verdicts:
        print(f"  - {v.status:11s} 置信={v.confidence:.2f} 层级={v.tier}")
        print(f"     断言：{v.claim.text}")
        print(f"     备注：{v.note}")

    if any(c.kind == "advice" for c in claims):
        print("\n[建议层 rubric]")
        for k, ok in advice_rubric(original).items():
            print(f"  - {k}: {'通过' if ok else '不通过'}")

    print("\n[修订稿]")
    if backend:
        revised = backend.llm_revise(original, verdicts)
    else:
        revised = revise(original, verdicts, cfg)
    print(revised)
    print("=" * 64)
    print("演示结束。接真实模型：python3 demo_dual_agent.py --llm（读 DEEPSEEK_API_KEY）。")
    print("详见 README.md")


if __name__ == "__main__":
    main()
