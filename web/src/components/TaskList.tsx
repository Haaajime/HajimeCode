import type { TaskSummary } from '../api'

interface Props {
  tasks: TaskSummary[]
  selectedId: string | null
  onSelect: (id: string) => void
}

const STATUS_STYLE: Record<string, string> = {
  running: 'bg-sky-500/15 text-sky-300 border-sky-800',
  done: 'bg-emerald-500/15 text-emerald-300 border-emerald-800',
  failed: 'bg-rose-500/15 text-rose-300 border-rose-800',
}

export function TaskList({ tasks, selectedId, onSelect }: Props) {
  if (tasks.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-slate-800 p-4 text-center text-xs text-slate-500">
        还没有任务，先在上面提交一个。
      </p>
    )
  }

  return (
    <ul className="scroll-thin max-h-[38vh] space-y-1.5 overflow-y-auto pr-1">
      {tasks.map((item) => {
        const active = item.id === selectedId
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onSelect(item.id)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition ${
                active
                  ? 'border-sky-700 bg-sky-950/40'
                  : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="mono text-[11px] text-slate-500">{item.id}</span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${
                    STATUS_STYLE[item.status] ?? 'border-slate-700 text-slate-400'
                  }`}
                >
                  {item.status}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs text-slate-300">{item.task}</p>
              <p className="mono mt-1 text-[10px] text-slate-500">
                {item.budget.steps} 步 · ¥{item.budget.cost_cny.toFixed(4)}
              </p>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
