// DSH workflow 版：actor → verifier（真实 web_search）→ revisor
// 用法：把这个脚本体交给 DSH 的 workflow 工具，args = { question: "你的问题" }
// 与 demo_dual_agent.py 的区别：这里是真模型、真搜索，跑一次约 3 个子 agent。

const q = args.question;

const actor = await agent(
  `你是 actor。用中文回答下面问题，150 字以内，像给同学解释一样直接说。问题：${q}`,
  { label: "actor" }
);

const verifier = await agent(
  `你是 verifier。下面是另一个 AI 的回答：\n---\n${actor}\n---\n任务：抽出最多 3 条最需要核查的断言（优先数字、引用、人名、行动建议），用 web_search 逐条查证。只输出 JSON。`,
  {
    label: "verifier",
    schema: {
      type: "object",
      additionalProperties: false,
      required: ["claims"],
      properties: {
        claims: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            required: ["claim", "kind", "verdict", "evidence", "confidence"],
            properties: {
              claim: { type: "string" },
              kind: { type: "string", enum: ["fact", "citation", "advice"] },
              verdict: { type: "string", enum: ["supported", "unsupported", "refuted"] },
              evidence: { type: "string" },
              confidence: { type: "number" },
            },
          },
        },
      },
    },
  }
);

const revised = await agent(
  `你是 revisor。根据核查结果修订回答：没有出处的引用删掉或降级为"推测"，数字/事实错误直接改对，绝对化措辞软化，建议补上替代方案。150 字以内。\n原回答：${actor}\n核查结果：${JSON.stringify(verifier.claims)}`,
  { label: "revisor" }
);

return { question: q, draft: actor, verdicts: verifier.claims, revised };
