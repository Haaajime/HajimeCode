import { useEffect, useRef, useState } from 'react'

import { EXAMPLE_GROUPS } from '../examples'
import type { ModelOption, WorkspacePreset } from '../api'
import { WorkspacePicker } from './WorkspacePicker'

export interface SubmitPayload {
  task: string
  workspace: string
  model: string
}

interface Props {
  onSubmit: (payload: SubmitPayload) => Promise<void>
  disabled: boolean
  models: ModelOption[]
  defaultModel: string
  hasApiKey: boolean
  presets: WorkspacePreset[]
}

export function TaskForm({ onSubmit, disabled, models, defaultModel, hasApiKey, presets }: Props) {
  const [task, setTask] = useState('')
  const [workspace, setWorkspace] = useState('')

  // ⚠️ 不能写成 useState(defaultModel)。
  // defaultModel 首次渲染时还是空串（模型列表是异步到达的），那样 React 状态会永远停在空串；
  // 而浏览器会把第一个 <option> 显示成"已选中" —— 于是界面显示「无模型模式」，
  // 实际提交却因 model 为空而被前端省略、服务端回退到默认模型，产生真实费用。
  // 这正是用户遇到的「无模型模式跑出 ¥0.0175」。
  const [model, setModel] = useState('')
  const userPicked = useRef(false)

  useEffect(() => {
    if (userPicked.current) return
    if (defaultModel && models.some((item) => item.id === defaultModel)) {
      setModel(defaultModel)
    }
  }, [defaultModel, models])

  const selected = models.find((item) => item.id === model)
  // 没有有效选择就不许提交 —— 这是"静默跑错模型"的最后一道闸
  const blockReason =
    models.length === 0
      ? '模型列表尚未就绪'
      : selected === undefined
        ? '尚未选定模型'
        : !selected.available
          ? '该模型未配置密钥，无法真实调用'
          : null
  const blocked = blockReason !== null
  const isStub = selected?.kind === 'stub'

  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!task.trim() || blocked) return
    setError(null)
    try {
      await onSubmit({ task: task.trim(), workspace: workspace.trim(), model })
      setTask('')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }

  function applyExample(taskText: string, workspaceKey?: string) {
    setTask(taskText)
    if (!workspaceKey) return
    const preset = presets.find((item) => item.key === workspaceKey)
    if (preset) setWorkspace(preset.path)
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-semibold tracking-wide text-slate-300">新建任务</h2>

      <textarea
        value={task}
        onChange={(event) => setTask(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) void submit()
        }}
        rows={4}
        placeholder="描述要 Agent 完成的任务…（⌘/Ctrl + Enter 提交）"
        className="w-full resize-none rounded-lg border border-slate-700 bg-slate-950/70 p-3 text-sm
                   text-slate-100 outline-none placeholder:text-slate-600 focus:border-sky-600"
      />

      <div className="mt-2">
        <div className="flex items-center justify-between gap-2">
          <label className="text-[11px] text-slate-500">模型</label>
          {isStub && <span className="text-[10px] text-amber-400">零 API 成本 · 结论不具参考性</span>}
          {selected?.kind === 'llm' && !hasApiKey && (
            <span className="text-[10px] text-rose-400">未配置密钥，无法真实调用</span>
          )}
        </div>
        <select
          value={model}
          onChange={(event) => {
            userPicked.current = true
            setModel(event.target.value)
          }}
          className="mono mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2
                     text-xs text-slate-300 outline-none focus:border-sky-600"
        >
          {/* 没有这一项时，浏览器会把第一个 model 选项显示成已选中，而 state 还是空串 —— 
              显示与实际提交的模型会不一致。保留占位项，让界面永远说真话。 */}
          {model === '' && <option value="">（模型加载中…）</option>}
          {models.map((item) => (
            <option key={item.id} value={item.id} disabled={!item.available}>
              {item.label}
              {item.available ? '' : '（不可用）'}
            </option>
          ))}
        </select>
      </div>

      <WorkspacePicker value={workspace} presets={presets} onChange={setWorkspace} />

      {/* 提交前把"将用哪个模型"再明说一次 —— 这是唯一会产生真实费用的选择 */}
      <p
        className={`mt-3 rounded-md px-2 py-1.5 text-[11px] ${
          isStub
            ? 'bg-slate-800/60 text-slate-400'
            : 'bg-amber-950/40 text-amber-300/90'
        }`}
      >
        {blocked ? (
          <span className="text-rose-300">无法提交：{blockReason}</span>
        ) : isStub ? (
          <>将以「无模型模式」提交 —— 不调用大模型，零成本。</>
        ) : (
          <>
            将以 <span className="mono">{selected?.label}</span> 提交 —— 会调用真实大模型并产生费用。
          </>
        )}
      </p>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={disabled || blocked || !task.trim()}
        className="mt-2 w-full rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white
                   transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700
                   disabled:text-slate-400"
      >
        {disabled ? '执行中…' : '提交任务'}
      </button>

      {error && (
        <p className="mt-2 rounded-md bg-rose-950/60 px-2 py-1.5 text-xs text-rose-300">{error}</p>
      )}

      <div className="mt-4 border-t border-slate-800 pt-3">
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="text-xs font-semibold tracking-wide text-slate-400">默认任务场景</h3>
          <span className="text-[10px] text-slate-600">
            点击填入完整任务，并自动切到对应工作目录
          </span>
        </div>

        <div className="scroll-thin max-h-[42vh] space-y-3 overflow-y-auto pr-1">
          {EXAMPLE_GROUPS.map((group) => (
            <div key={group.title}>
              <p className="text-[11px] font-medium text-slate-400">{group.title}</p>
              <p className="mb-1 text-[10px] leading-snug text-slate-600">{group.hint}</p>
              <ul className="space-y-1">
                {group.items.map((example) => (
                  <li key={example.task}>
                    <button
                      type="button"
                      onClick={() => applyExample(example.task, example.workspaceKey)}
                      className="w-full rounded-lg border border-slate-800 bg-slate-950/40 px-2 py-1.5
                                 text-left transition hover:border-slate-600 hover:bg-slate-900"
                    >
                      <span className="mono text-[10px] text-sky-400">{example.label}</span>
                      <p className="mt-0.5 text-[11px] leading-snug text-slate-300">
                        {example.task}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
