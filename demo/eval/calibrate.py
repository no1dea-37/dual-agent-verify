#!/usr/bin/env python3
"""置信度校准（isotonic / PAVA 保序回归）。

问题：模型自己报的 confidence 通常偏乐观（比如 0.9 实际只有 0.6 对）。
做法：拿一批带标注的评测结果 (confidence, 是否正确)，拟合一条单调不减的映射，
把原始置信度换成「实测正确率」。

用法：
    python3 calibrate.py --selftest     # 内置样例自检
在 evaluate.py 里通过 --calibrate 使用。
"""

import sys


def _pava(points):
    """保序回归（Pool Adjacent Violators）。

    points: [(x, y, w)]，按 x 升序；y 是 0/1 观测，w 是样本数。
    返回 [(xmin, xmax, 均值)]，块内 y 的均值单调不减。
    """
    blocks = []  # [xmin, xmax, sum_y, weight]
    for x, y, w in points:
        blocks.append([x, x, y * w, w])
        while len(blocks) > 1:
            prev, cur = blocks[-2], blocks[-1]
            if prev[2] / prev[3] <= cur[2] / cur[3]:
                break
            prev[1] = cur[1]
            prev[2] += cur[2]
            prev[3] += cur[3]
            blocks.pop()
    return [(b[0], b[1], b[2] / b[3]) for b in blocks]


def fit(samples):
    """samples: [(confidence, correct)] → 校准器（list of blocks）。"""
    if not samples:
        return []
    agg = {}
    for conf, ok in samples:
        c = round(float(conf), 3)
        s = agg.setdefault(c, [0, 0])
        s[0] += 1 if ok else 0
        s[1] += 1
    points = [(c, s[0] / s[1], s[1]) for c, s in sorted(agg.items())]
    return _pava(points)


def apply(blocks, conf):
    """把原始置信度映射为校准值；超出范围取端点。"""
    if not blocks:
        return conf
    for lo, hi, val in blocks:
        if lo <= conf <= hi:
            return val
    if conf < blocks[0][0]:
        return blocks[0][2]
    return blocks[-1][2]


def brier(samples, transform=None):
    """Brier 分数（越小越好）：mean((p - y)^2)。transform 是校准器或 None。"""
    if not samples:
        return 0.0
    total = 0.0
    for conf, ok in samples:
        p = apply(transform, conf) if transform else conf
        total += (p - (1.0 if ok else 0.0)) ** 2
    return total / len(samples)


def _selftest():
    # 构造一个「过度自信」的数据集：conf 0.9 实际只有 50% 对
    data = [(0.9, i % 2 == 0) for i in range(20)] + [(0.5, i % 4 == 0) for i in range(20)]
    blocks = fit(data)
    cal = [apply(blocks, c) for c in (0.5, 0.9)]
    print("块：", [(lo, hi, round(v, 2)) for lo, hi, v in blocks])
    assert all(blocks[i][2] <= blocks[i + 1][2] for i in range(len(blocks) - 1)), "未保持单调"
    assert apply(blocks, 0.9) < 0.9, "过度自信没有被压低"
    assert brier(data, blocks) < brier(data), "校准后 Brier 没有下降"
    print("自检通过：brier 原始=%.4f 校准=%.4f" % (brier(data), brier(data, blocks)))
    print("校准值：", [round(c, 2) for c in cal])


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print("用法：python3 calibrate.py --selftest")
