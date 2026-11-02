#!/usr/bin/env python3
"""检查 demo/prompts.py 与 index.js 的 SYSTEM_PROMPT 是否一致（防 prompt 漂移）。

用法：python3 check_prompts.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
ROOT = os.path.dirname(DEMO)
if DEMO not in sys.path:
    sys.path.insert(0, DEMO)

import prompts  # noqa: E402


def main():
    js_path = os.path.join(ROOT, "index.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    m = re.search(r"const SYSTEM_PROMPT = `([\s\S]*?)`", js)
    if not m:
        print("index.js 里找不到 SYSTEM_PROMPT")
        return 1
    js_prompt = m.group(1).strip()
    py_prompt = prompts.VERIFY_SYSTEM.strip()
    if js_prompt != py_prompt:
        print("prompt 不一致：")
        for i, (a, b) in enumerate(zip(js_prompt.splitlines(), py_prompt.splitlines())):
            if a != b:
                print(f"  第 {i + 1} 行不同")
                print(f"    js: {a}")
                print(f"    py: {b}")
        if len(js_prompt.splitlines()) != len(py_prompt.splitlines()):
            print(f"  行数不同：js={len(js_prompt.splitlines())} py={len(py_prompt.splitlines())}")
        return 1
    print("一致：index.js 与 demo/prompts.py 的 SYSTEM_PROMPT 相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
