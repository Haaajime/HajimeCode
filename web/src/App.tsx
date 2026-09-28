import { useCallback, useEffect, useRef, useState } from 'react'

import {
  REQUIRED_API_VERSION,
  createTask,
  getHealth,
  listModels,
  listPresets,
  listTasks,
  subscribe,
} from './api'
import type { Budget, ModelOption, TaskEvent, TaskSummary, WorkspacePreset } from './api'
import { CostBar } from './components/CostBar'
import { TaskForm } from './components/TaskForm'
import type { SubmitPayload } from './components/TaskForm'
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
  const [models, setModels] = useState<ModelOption[]>([])
  const [defaultModel, setDefaultModel] = useState('')
  const [hasApiKey, setHasApiKey] = useState(false)
  const [presets, setPresets] = useState<WorkspacePreset[]>([])
  // 启动期（模型列表 / 工作区预设）的失败必须让用户看见 ——
  // 静默吞掉只会得到一个"空白下拉框"，用户完全无从判断哪里出了问题。
  const [bootError, setBootError] = useState<string | null>(null)
  const [serverOutdated, setServerOutdated] = useState(false)

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
    const note = (label: string, exc: unknown) => {
      const message = exc instanceof Error ? exc.message : String(exc)
      setBootError((previous) => previous ?? `${label}：${message}`)
    }

    void (async () => {
      try {
        const health = await getHealth()
        setModel(health.model)
        if (
          typeof health.api_version !== 'number' ||
          health.api_version < REQUIRED_API_VERSION
        ) {
          setServerOutdated(true)
        }
      } catch (exc) {
        setModel('')
        note('无法连接服务端', exc)
      }

      try {
        const payload = await listModels()
        setModels(payload.models)
        setDefaultModel(payload.default)
        setHasApiKey(payload.has_api_key)
      } catch (exc) {
        note('模型列表加载失败', exc)
      }

      try {
        const payload = await listPresets()
        setPresets(payload.workspaces)
      } catch (exc) {
        note('工作区预设加载失败', exc)
      }

      void refreshTasks()
    })()
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

  async function handleSubmit(payload: SubmitPayload) {
    setBusy(true)
    setError(null)
    try {
      const id = await createTask(payload.task, payload.workspace || undefined, payload.model)
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

      {serverOutdated && (
        <div className="mb-3 rounded-lg border border-amber-800 bg-amber-950/50 px-3 py-2 text-xs text-amber-200">
          <strong className="font-medium">服务端接口过旧。</strong>
          当前页面需要更新的接口（如 <code className="mono">/api/models</code>、
          <code className="mono">/api/fs/dirs</code>），但服务端没有提供 —— 大概率是旧的
          <code className="mono"> hajime2code-web </code>
          进程还占着端口。请结束它并重启（
          <code className="mono">uv run hajime2code-web</code>）后刷新本页。
        </div>
      )}

      {bootError && (
        <div className="mb-3 rounded-lg bg-rose-950/60 px-3 py-2 text-xs text-rose-300">
          {bootError}
        </div>
      )}

      {error && (
        <div className="mb-3 rounded-lg bg-rose-950/60 px-3 py-2 text-xs text-rose-300">{error}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        <div className="space-y-3">
          <TaskForm
            onSubmit={handleSubmit}
            disabled={busy}
            models={models}
            defaultModel={defaultModel}
            hasApiKey={hasApiKey}
            presets={presets}
          />
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
