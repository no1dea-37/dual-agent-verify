/**
 * dsh-verify — 双 agent 验证器插件骨架。
 * 注册工具 verify_answer：把一段回答交给 verifier 抽断言并核查，返回判定与修订稿。
 *
 * 现状：verifier 只调当前默认模型（无联网检索）。
 * 接真实搜索见 README 的 TODO；结构上只需替换 verifyWithModel 里的证据来源。
 */
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'dsh-verify'
export const inject = ['tools', 'llm', 'agentDefaultModel']

const SYSTEM_PROMPT = `你是 verifier（核查员）。任务：从用户给到的回答里抽出最多 5 条最需要核查的断言，逐条判断：
- kind: fact（数字/事实）/ citation（引用、某人说过、承诺）/ advice（建议、判断）
- verdict: supported（有把握，可给出处）/ unsupported（查不到出处）/ refuted（与已知事实冲突）
- evidence: 一句话依据；不能联网核实时就写「模型知识，未联网核实」
- confidence: 0 到 1
然后给出修订稿：没有出处的引用删掉或降级为「推测」，事实错误改对，绝对化措辞软化，建议补一两个替代方案。
只输出 JSON，不要输出其他文字：
{"claims":[{"claim":"","kind":"fact","verdict":"supported","evidence":"","confidence":0.0}],"revised":""}`

export function apply(ctx, config) {
  const register = () => ctx.tools.register(defineTool({
    name: 'verify_answer',
    description: '双 agent 验证：核查一段回答里的事实/引用/建议，返回逐条判定与修订稿。给出重要建议、引用或数字前自查用。',
    parameters: {
      text: { type: 'string', description: '要核查的回答草稿' },
      strict: { type: 'boolean', description: '严格模式：连建议也逐条核查（默认只查事实与引用）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: value.message }],
    },
    async execute(args) {
      const text = String(args.text || '').trim()
      if (!text) return { ok: false, message: '没有可核查的内容' }
      const strict = args.strict === true
      try {
        const raw = await verifyWithModel(ctx, text, strict)
        const parsed = parseJson(raw)
        if (!parsed || !Array.isArray(parsed.claims)) {
          return { ok: false, message: 'verifier 没有返回可解析的 JSON：\n' + raw.slice(0, 400) }
        }
        const lines = parsed.claims.map((c, i) => {
          const conf = typeof c.confidence === 'number' ? c.confidence.toFixed(2) : '?'
          return `${i + 1}. [${c.kind}] ${c.verdict}（置信 ${conf}）\n   断言：${c.claim}\n   依据：${c.evidence}`
        })
        const message = [
          '【verifier 结论】',
          lines.join('\n') || '（没有需要核查的断言）',
          '',
          '【修订稿】',
          parsed.revised || '（未给出修订稿）',
        ].join('\n')
        return { ok: true, claims: parsed.claims, revised: parsed.revised || '', message }
      } catch (error) {
        return { ok: false, message: '核查失败：' + (error instanceof Error ? error.message : String(error)) }
      }
    },
  }))

  // 冷启动兜底：tools 服务未就绪时，等它 inject 就绪再注册（与 dsh-meme 同一姿势）
  if (typeof ctx.inject === 'function') {
    try {
      ctx.inject(['tools'], () => register())
    } catch {
      register()
    }
  } else {
    register()
  }
}

async function verifyWithModel(ctx, text, strict) {
  const sel = ctx.agentDefaultModel && typeof ctx.agentDefaultModel.currentSelection === 'function'
    ? ctx.agentDefaultModel.currentSelection()
    : null
  const llm = ctx.get('llm')
  if (!llm || !sel || !sel.provider || !sel.model) throw new Error('未配置模型')

  const base = await llm.resolveCallConfig({ provider: sel.provider, model: sel.model, maxTokens: 2048 })
  const prepared = await llm.prepareCall(base)

  const user = (strict ? '【严格模式：建议也逐条核查】\n' : '') + text
  let out = ''
  for await (const chunk of prepared.stream({
    ...base,
    messages: [
      { role: 'system', content: SYSTEM_PROMPT },
      { role: 'user', content: user },
    ],
  })) {
    if (chunk.type === 'text-delta') out += chunk.text
    else if (chunk.type === 'finish' && chunk.reason && chunk.reason.kind === 'error') {
      throw new Error('模型调用失败：' + JSON.stringify(chunk.reason.failure || {}))
    }
  }
  return out
}

function parseJson(raw) {
  const m = /\{[\s\S]*\}/.exec(raw)
  if (!m) return null
  try {
    return JSON.parse(m[0])
  } catch {
    return null
  }
}
