import { useCallback, useEffect, useRef, useState } from 'react'

import { createTask, getHealth, listTasks, subscribe } from './api'
import type { Budget, TaskEvent, TaskSummary } from './api'
import { CostBar } from './components/CostBar'
import { TaskForm } from './components/TaskForm'
import { TaskList } from './components/TaskList'
import { Timeline } from './components/Timeline'

export default function App() {
  const [model, setModel] = useState('')
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [budget, setBudget] = useState<Budget | null>(null)
  const [live, setLive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 记录"当前真正订阅的任务"，避免切换任务时旧连接的事件写进新视图
  const activeId = useRef<string | null>(null)

  const refreshTasks = useCallback(async () => {
    try {
      setTasks(await listTasks())
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }, [])

  useEffect(() => {
    void getHealth()
      .then((health) => setModel(health.model))
      .catch(() => setModel(''))
    void refreshTasks()
  }, [refreshTasks])

  useEffect(() => {
    if (!selectedId) return
    activeId.current = selectedId
    setEvents([])
    setBudget(null)
    setLive(true)

    const unsubscribe = subscribe(selectedId, {
      onEvent: (event) => {
        if (activeId.current !== selectedId) return
        setEvents((previous) => [...previous, event])
        if (event.type === 'budget.updated') {
          setBudget(event.data.total as Budget)
        }
        if (event.type === 'task.finished' && event.data.budget) {
          setBudget(event.data.budget as Budget)
        }
      },
      onClose: () => {
        if (activeId.current !== selectedId) return
        setLive(false)
        void refreshTasks()
      },
    })

    return unsubscribe
  }, [selectedId, refreshTasks])

  const selected = tasks.find((item) => item.id === selectedId) ?? null

  async function handleSubmit(task: string, workspace: string) {
    setBusy(true)
    setError(null)
    try {
      const id = await createTask(task, workspace || undefined)
      await refreshTasks()
      setSelectedId(id)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
      throw exc
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl p-4 lg:p-6">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Hajime2Code</h1>
          <p className="text-xs text-slate-500">
            基于 LangGraph 的编码 Agent 运行时 · 实时执行控制台
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`h-2 w-2 rounded-full ${live ? 'animate-pulse bg-sky-400' : 'bg-slate-600'}`}
          />
          <span className="text-slate-400">{live ? '执行中' : '空闲'}</span>
          {model && (
            <span className="mono rounded border border-slate-700 px-2 py-0.5 text-slate-400">
              {model}
            </span>
          )}
        </div>
      </header>

      {error && (
        <div className="mb-3 rounded-lg bg-rose-950/60 px-3 py-2 text-xs text-rose-300">{error}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <div className="space-y-3">
          <TaskForm onSubmit={handleSubmit} disabled={busy} />
          <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-slate-300">任务列表</h2>
            <TaskList tasks={tasks} selectedId={selectedId} onSelect={setSelectedId} />
          </section>
        </div>

        <div className="space-y-3">
          <CostBar budget={budget} />

          {selected && (
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <div className="mono mb-1 flex items-center justify-between gap-3 text-[11px] text-slate-500">
                <span>{selected.id}</span>
                <span className="truncate">{selected.workspace}</span>
              </div>
              <p className="text-sm text-slate-200">{selected.task}</p>
              {selected.plan.length > 0 && (
                <ol className="mt-2 list-inside list-decimal space-y-0.5 text-xs text-slate-400">
                  {selected.plan.map((step, index) => (
                    <li key={`${index}-${step}`}>{step}</li>
                  ))}
                </ol>
              )}
            </section>
          )}

          <Timeline events={events} live={live} />
        </div>
      </div>
    </div>
  )
}
