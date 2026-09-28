import type { TaskEvent } from '../api'

type Tone = 'muted' | 'info' | 'ok' | 'warn' | 'error' | 'accent'

export type TimelineItem =
  | { kind: 'row'; key: string; tone: Tone; label: string; text: string }
  | { kind: 'stream'; key: string; node: string; text: string }

const TONE_CLASS: Record<Tone, string> = {
  muted: 'border-slate-800 text-slate-400',
  info: 'border-sky-900 text-sky-200',
  ok: 'border-emerald-900 text-emerald-200',
  warn: 'border-amber-900 text-amber-200',
  error: 'border-rose-900 text-rose-200',
  accent: 'border-violet-900 text-violet-200',
}

function preview(value: unknown, limit = 400): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function toRow(event: TaskEvent): TimelineItem {
  const data = event.data
  const node = String(data.node ?? '')
  const key = `e${event.seq}`

  switch (event.type) {
    case 'task.created':
      return { kind: 'row', key, tone: 'accent', label: '创建', text: String(data.task ?? '') }
    case 'node.started':
      return { kind: 'row', key, tone: 'muted', label: '▶ 节点', text: node }
    case 'node.finished': {
      const error = data.error
      return error
        ? { kind: 'row', key, tone: 'error', label: '✖ 节点', text: `${node} — ${preview(error)}` }
        : { kind: 'row', key, tone: 'muted', label: '■ 节点', text: node }
    }
    case 'tool.started':
      return {
        kind: 'row',
        key,
        tone: 'warn',
        label: '🔧 工具',
        text: `${String(data.name ?? '')} ${preview(data.args ?? {}, 200)}`,
      }
    case 'tool.finished': {
      const ok = data.ok !== false
      return {
        kind: 'row',
        key,
        tone: ok ? 'ok' : 'error',
        label: ok ? '↳ 返回' : '↳ 失败',
        text: `${String(data.name ?? '')}: ${preview(data.preview ?? '')}`,
      }
    }
    case 'assistant.message':
      return { kind: 'row', key, tone: 'info', label: '🤖 模型', text: preview(data.text ?? '') }
    case 'task.finished': {
      const status = String(data.status ?? '')
      return {
        kind: 'row',
        key,
        tone: status === 'done' ? 'ok' : 'error',
        label: `结束 · ${status}`,
        text: preview(data.summary ?? ''),
      }
    }
    case 'error':
      return { kind: 'row', key, tone: 'error', label: '错误', text: preview(data.message ?? '') }
    default:
      return { kind: 'row', key, tone: 'muted', label: event.type, text: '' }
  }
}

/**
 * 把事件流折叠成可渲染的时间线。
 *
 * - 连续且同节点的 `llm.token` 合并成一条会持续增长的流式文本；
 * - `budget.updated` 只更新顶部指标，不进时间线；
 * - 某节点若有 token 流，则它随后的 `assistant.message`（同一份内容的完整版）不再重复展示。
 */
export function groupEvents(events: TaskEvent[]): TimelineItem[] {
  const streamedNodes = new Set<string>()
  for (const event of events) {
    if (event.type === 'llm.token') streamedNodes.add(String(event.data.node ?? '?'))
  }

  const items: TimelineItem[] = []
  let open: Extract<TimelineItem, { kind: 'stream' }> | null = null

  const flush = () => {
    if (open) {
      items.push(open)
      open = null
    }
  }

  for (const event of events) {
    if (event.type === 'llm.token') {
      const node = String(event.data.node ?? '?')
      const text = String(event.data.text ?? '')
      if (open && open.node === node) {
        open.text += text
      } else {
        flush()
        open = { kind: 'stream', key: `s${event.seq}`, node, text }
      }
      continue
    }
    if (event.type === 'budget.updated') continue
    if (event.type === 'assistant.message' && streamedNodes.has(String(event.data.node ?? '?'))) {
      continue
    }
    flush()
    items.push(toRow(event))
  }
  flush()
  return items
}

export function Timeline({ events, live }: { events: TaskEvent[]; live: boolean }) {
  const items = groupEvents(events)

  return (
    <div className="scroll-thin h-[52vh] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      {items.length === 0 && (
        <p className="py-10 text-center text-xs text-slate-600">
          {live ? '等待事件…' : '选择或提交一个任务，这里会实时显示 Agent 的每一步。'}
        </p>
      )}

      <ul className="space-y-1">
        {items.map((item) =>
          item.kind === 'stream' ? (
            <li
              key={item.key}
              className="rounded-lg border border-violet-900/60 bg-violet-950/20 px-2.5 py-1.5"
            >
              <div className="flex items-center gap-2 text-[10px] text-violet-400">
                <span>⌨ {item.node}</span>
                {live && <span className="animate-pulse">● 流式输出中</span>}
              </div>
              <p className="mt-1 whitespace-pre-wrap text-xs text-violet-100">{item.text}</p>
            </li>
          ) : (
            <li
              key={item.key}
              className={`rounded-lg border-l-2 px-2.5 py-1.5 ${TONE_CLASS[item.tone]}`}
            >
              <div className="flex gap-2 text-[11px]">
                <span className="shrink-0 opacity-70">{item.label}</span>
                <span className="whitespace-pre-wrap break-all">{item.text}</span>
              </div>
            </li>
          ),
        )}
      </ul>
    </div>
  )
}
