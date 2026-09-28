import type { Budget } from '../api'

interface Props {
  budget: Budget | null
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-2.5 py-1.5">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className="mono text-sm text-slate-200">{value}</div>
    </div>
  )
}

export function CostBar({ budget }: Props) {
  const current: Budget =
    budget ?? {
      steps: 0,
      llm_calls: 0,
      tokens_in: 0,
      tokens_out: 0,
      cache_hit_tokens: 0,
      cache_miss_tokens: 0,
      cost_cny: 0,
    }

  const hitRate =
    current.tokens_in > 0 ? `${((current.cache_hit_tokens / current.tokens_in) * 100).toFixed(0)}%` : '—'

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Metric label="步数 / LLM 调用" value={`${current.steps} / ${current.llm_calls}`} />
      <Metric label="tokens 输入 / 输出" value={`${current.tokens_in} / ${current.tokens_out}`} />
      <Metric
        label="缓存命中率"
        value={hitRate}
        // 命中率是 E4「压缩 ↔ 缓存对抗」实验的核心观测量
      />
      <Metric label="累计成本" value={`¥${current.cost_cny.toFixed(4)}`} />
    </div>
  )
}
