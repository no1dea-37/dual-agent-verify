# dual-agent-verify — 双 agent 验证器

一个 actor（正常回答）+ 一个 verifier（抽断言、核查事实/引用/建议）的验证器，
提供 DSH 插件 `dsh-verify`，并带可跑的 demo。

仓库结构：

- 根目录 = DSH 插件包（`dsh-verify`）：`package.json` / `index.js`
- `demo/` = 验证器 demo：`demo_dual_agent.py`（零依赖 mock 证据库）、`workflow_demo.js`（DSH workflow 三 agent 版）

## 插件：verify_answer

注册工具 `verify_answer(text, strict?)`：把一段回答交给 verifier 模型，抽最多 5 条断言
（事实 / 引用 / 建议），逐条判 `supported / unsupported / refuted`，带置信度和修订稿。

- 不联网（verifier 只能靠模型知识，证据会标「未联网核实」）。
- 不改文件、不替你行动，只给核查结果。

### 装进 DSH profile（本地开发）

```bash
cd ~/.dsh/profiles/desktop
pnpm add "file:/path/to/dual-agent-verify"
```

然后把 `dsh-verify` 加进 profile 的 `dsh.profile.bundles`，重启 DSH。

**风险**：改 profile 依赖后插件加载失败会让 DSH 起不来；装前备份
`~/.dsh/profiles/desktop/package.json`。

### 接真实搜索（TODO）

插件里没有 agent 的工具上下文，不能直接调 `web_search`；需要自带搜索 API
（Tavily / Serper / Bing 等），把证据喂进 verifier。免费过渡：模型知识 + 置信度阈值，
低置信高风险断言列出来人工核。

## demo

```bash
cd demo
python3 demo_dual_agent.py            # 默认：双 agent，只验证高风险断言（mock 证据）
python3 demo_dual_agent.py --strict   # 全量核查 + 建议层 rubric
python3 demo_dual_agent.py --off      # 单 agent 对照（关闭验证）
python3 demo_dual_agent.py --llm      # actor/verifier/revisor 全走真模型
```

`--llm` 读环境变量：`DEEPSEEK_API_KEY`（必填）、`LLM_BASE_URL`（默认
`https://api.deepseek.com/v1`）、`LLM_MODEL`（默认 `deepseek-chat`）、
`TAVILY_API_KEY`（可选，设了 verifier 就用 Tavily 搜真证据，不设退回 mock 证据库）。

`workflow_demo.js` 是 DSH workflow 版：actor → verifier（真 web_search）→ revisor。

### 评测（demo/eval）

```bash
cd demo/eval
python3 evaluate.py                 # 无 key：启发式 baseline，验证评测流程（37 条事实/引用 + 3 条建议）
python3 evaluate.py --llm           # 真模型逐条核查（读 DEEPSEEK_API_KEY）
python3 evaluate.py --calibrate     # 额外做置信度校准（保序回归，留出集评估 Brier）
python3 calibrate.py --selftest     # 校准模块自检
python3 check_prompts.py            # 检查 demo/prompts.py 与 index.js 的 SYSTEM_PROMPT 是否一致
```

评测集 `demo/eval/cases.jsonl` 是 40 条人工标注（supported / unsupported / refuted / advice），
输出混淆矩阵、precision/recall/F1 与置信度分箱。prompt 文本集中在 `demo/prompts.py`，插件里是同一份副本，
`check_prompts.py` 做字符串比对防漂移。

## 已知边界

- 建议层只做 rubric 打分（替代方案 / 前提假设 / 信息充分性 / 确定性 / 边界 / 利益），不判「对错」。
- 每次调用 = 1 次模型调用；按次成本记在账上。
- 模型未配置时工具直接报错，不会静默假装通过。
