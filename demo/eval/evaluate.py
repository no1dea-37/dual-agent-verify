#!/usr/bin/env python3
"""双 agent 验证器评测：跑 cases.jsonl，算混淆矩阵、精确率/召回率、置信度校准。

用法：
    python3 evaluate.py            # 无 key：启发式 baseline（稻草人，仅验证评测流程）
    python3 evaluate.py --llm      # 真模型逐条核查（需 DEEPSEEK_API_KEY）
    python3 evaluate.py --llm --limit 10   # 先跑前 10 条试水

输出：
    终端表格 + eval/report.md

注意：ground truth 是人工标注（cases.jsonl 的 label），只覆盖事实/引用两类；
建议（advice）不进精确率，只统计条数。
"""

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases.jsonl")
REPORT = os.path.join(HERE, "report.md")

LABELS = ["supported", "unsupported", "refuted"]


def load_cases():
    cases = []
    with open(CASES, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def baseline_verify(claim):
    """无 key 时的稻草人：只按关键词给判断，专门用来跑通评测管线。"""
    if any(k in claim for k in ("说过", "承诺", "据说", "邮件里", "留一个窗口")):
        return {"status": "unsupported", "confidence": 0.45, "evidence_url": "", "snippet": ""}
    return {"status": "supported", "confidence": 0.55, "evidence_url": "", "snippet": ""}


def llm_verify(claim):
    import real_backend

    return real_backend.llm_verify_claim(claim)


def evaluate(cases, verify):
    rows = []
    skipped = 0
    for c in cases:
        if c["label"] == "advice":
            skipped += 1
            continue
        try:
            pred = verify(c["claim"])
        except Exception as e:  # 单条失败不中断整轮
            pred = {"status": "error", "confidence": 0.0, "evidence_url": "", "snippet": str(e)[:80]}
        rows.append(
            {
                "id": c["id"],
                "claim": c["claim"],
                "label": c["label"],
                "pred": pred["status"],
                "confidence": float(pred.get("confidence", 0.0)),
                "url": pred.get("evidence_url", ""),
                "snippet": pred.get("snippet", ""),
            }
        )
    return rows, skipped


def metrics(rows):
    valid = [r for r in rows if r["pred"] in LABELS]
    errors = len(rows) - len(valid)
    n = len(valid)
    cm = {t: Counter() for t in LABELS}
    for r in valid:
        cm[r["label"]][r["pred"]] += 1

    correct = sum(1 for r in valid if r["pred"] == r["label"])
    acc = correct / n if n else 0.0

    tp = sum(1 for r in valid if r["label"] == "supported" and r["pred"] == "supported")
    fp = sum(1 for r in valid if r["label"] != "supported" and r["pred"] == "supported")
    fn = sum(1 for r in valid if r["label"] == "supported" and r["pred"] != "supported")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    bins = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]
    calib = []
    for lo, hi in bins:
        sel = [r for r in valid if lo <= r["confidence"] < hi]
        acc_bin = sum(1 for r in sel if r["pred"] == r["label"]) / len(sel) if sel else 0.0
        calib.append((lo, hi, len(sel), acc_bin))

    return {
        "n": n,
        "errors": errors,
        "acc": acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "cm": cm,
        "calib": calib,
    }


def fmt(m, skipped):
    lines = []
    lines.append(f"样本：{m['n']} 条（另有 {skipped} 条建议样本跳过，{m['errors']} 条预测失败）")
    lines.append(f"准确率：{m['acc']:.2%}")
    lines.append(f"supported 类：precision={m['precision']:.2f} recall={m['recall']:.2f} F1={m['f1']:.2f}")
    lines.append("")
    lines.append("混淆矩阵（行=标注，列=预测）：")
    header = "        " + "".join(f"{p:>12s}" for p in LABELS)
    lines.append(header)
    for lab in LABELS:
        row = "".join(f"{m['cm'][lab][p]:>12d}" for p in LABELS)
        lines.append(f"{lab:>11s} {row}")
    lines.append("")
    lines.append("置信度校准：")
    for lo, hi, n, acc in m["calib"]:
        lines.append(f"  [{lo:.2f}, {hi:.2f})  n={n:2d}  准确率={acc:.2%}")
    return "\n".join(lines)


def main():
    mode = "llm" if "--llm" in sys.argv else "baseline"
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    cases = load_cases()
    if limit:
        cases = cases[:limit]

    if mode == "llm":
        if not os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("LLM_API_KEY"):
            print("--llm 需要 DEEPSEEK_API_KEY / LLM_API_KEY；先不加 --llm 跑 baseline 管线。")
            return
        verify = llm_verify
    else:
        verify = baseline_verify
        print("（无 key 模式：启发式 baseline，只验证评测流程，不代表模型能力）")

    rows, skipped = evaluate(cases, verify)
    m = metrics(rows)
    text = fmt(m, skipped)
    print(text)

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"# 验证器评测报告\n\n模式：{mode}\n\n```\n{text}\n```\n")
        f.write("\n## 逐条明细\n\n| id | 标注 | 预测 | 置信 | 断言 | 出处 |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['id']} | {r['label']} | {r['pred']} | {r['confidence']:.2f} | {r['claim']} | {r['url'][:40]} |\n")
    print(f"\n报告已写：{REPORT}")


if __name__ == "__main__":
    main()
