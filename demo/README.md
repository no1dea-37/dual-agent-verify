# 双 agent 验证器 demo（actor + verifier）

焦点：**事实引用** 和 **建议/判断** 的核查。零依赖、离线可跑，先看清控制流。

## 跑法

```bash
cd /path/to/dual-agent-verify
python3 demo_dual_agent.py            # 标准模式：只查高风险断言
python3 demo_dual_agent.py --strict   # 全部断言都查
python3 demo_dual_agent.py --off      # 对照组：单 agent，不核查
```

## 管线

```
用户问题
   │
   ▼
[actor] 出草稿 ──────────────────────────────┐
   │                                        │
   ▼                                        │
[monitor] 抽断言：fact / citation / advice   │
   │                                        │
   ▼                                        │
[verifier] 搜证据（mock）──► verdict ────────┤
   │  supported / unsupported / refuted     │
   ▼                                        │
[rubric] 建议层打分：替代方案 / 确定性 / 边界 / 利益
   │                                        │
   ▼                                        │
[controller] 修订：删无出处引用、软化绝对话 ◄──┘
   │
   ▼
修订稿 + 核查报告
```

## 参数（Config）

| 参数 | 默认 | 作用 |
|---|---|---|
| `verify_frequency` | `risky` | `all` 全查 / `risky` 只查 risk≥2 / `off` 关闭 |
| `confidence_threshold` | 0.60 | 低于此值视为「待确认」，措辞要降级 |
| `max_searches_per_claim` | 2 | 每条断言最多搜几次，控制成本与延迟 |
| `delay_budget_ms` | 800 | 缓冲验证允许的时延（流式场景） |
| `strictness` | 2 | 1 宽松 / 2 标准 / 3 严格 |

## 接真实模型

1. **换 actor**：`draft()` 改成调 LLM（或 DSH 的 `subagent`）；
2. **换 verifier**：`Verifier.lookup()` 改成调 `web_search` / 检索库，返回 `(tier, status, note)`；
3. **接 DSH**：用 `workflow` 工具把两段串起来——actor 子 agent 出草稿，verifier 子 agent 抽断言 + 搜网 + 回 verdict，actor 再改一版；
4. **变插件**：DSH 插件适合「注册工具」，不适合直接拦流式输出；这一层要么用 workflow 编排，要么等插件 API 支持 hook。

## 边界（别当它万能）

- 验证器自己也会错，尤其对「建议」只能打分，判不了对错；
- 建议层的 rubric 是启发式，真实场景要按领域重写判据；
- mock 证据库只为演示控制流，不是真实检索；
- 成本：双 agent 总 token 通常 1.3–2 倍；省钱靠「小模型验证 + 高风险抽样 + 工具化验证」。

## 演进方向

- [ ] 断言抽取换成 LLM（现在用正则）
- [ ] verifier 接真实检索（先缓存、后联网）
- [ ] 建议层加「最坏后果 / 可逆性」两项
- [ ] 输出「更正条」而不是静默改写
- [ ] 做成 DSH 子命令：`dsh verify --file answer.md`
