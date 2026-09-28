import { useState } from 'react'

interface Props {
  onSubmit: (task: string, workspace: string) => Promise<void>
  disabled: boolean
}

const EXAMPLES = [
  '用 glob 统计 src 下有多少个 .py 文件，只回答数字',
  '读 README.md 并总结这个项目是做什么的',
  '找出 tests 目录里最短的测试文件，说明它测了什么',
]

export function TaskForm({ onSubmit, disabled }: Props) {
  const [task, setTask] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!task.trim()) return
    setError(null)
    try {
      await onSubmit(task.trim(), workspace.trim())
      setTask('')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-semibold tracking-wide text-slate-300">新建任务</h2>

      <textarea
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void submit()
        }}
        rows={3}
        placeholder="描述要 Agent 完成的任务…（⌘/Ctrl + Enter 提交）"
        className="w-full resize-none rounded-lg border border-slate-700 bg-slate-950/70 p-3 text-sm
                   text-slate-100 outline-none placeholder:text-slate-600 focus:border-sky-600"
      />

      <input
        value={workspace}
        onChange={(e) => setWorkspace(e.target.value)}
        placeholder="工作目录（留空用服务端默认）"
        className="mono mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2
                   text-xs text-slate-300 outline-none placeholder:text-slate-600 focus:border-sky-600"
      />

      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => setTask(example)}
            className="rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-400
                       transition hover:border-slate-500 hover:text-slate-200"
          >
            {example.slice(0, 14)}…
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={disabled || !task.trim()}
        className="mt-3 w-full rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white
                   transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700
                   disabled:text-slate-400"
      >
        {disabled ? '执行中…' : '提交任务'}
      </button>

      {error && (
        <p className="mt-2 rounded-md bg-rose-950/60 px-2 py-1.5 text-xs text-rose-300">{error}</p>
      )}
    </section>
  )
}
