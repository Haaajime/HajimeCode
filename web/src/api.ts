/** 后端契约。字段与 `src/hajime2code/serve/events.py` / `store.py` 保持一致。 */

export interface Budget {
  steps: number
  llm_calls: number
  tokens_in: number
  tokens_out: number
  cache_hit_tokens: number
  cache_miss_tokens: number
  cost_cny: number
}

export interface Todo {
  id: string
  content: string
  status: string
}

export interface TaskSummary {
  id: string
  task: string
  workspace: string
  created_at: number
  status: string
  summary: string
  plan: string[]
  todos: Todo[]
  budget: Budget
}

export interface TaskEvent {
  seq: number
  task_id: string
  type: string
  ts: number
  data: Record<string, unknown>
}

export interface ModelOption {
  id: string
  label: string
  kind: 'stub' | 'llm'
  available: boolean
}

export interface ModelList {
  default: string
  stub_id: string
  has_api_key: boolean
  models: ModelOption[]
}

export interface WorkspacePreset {
  key: string
  label: string
  path: string
}

export interface Presets {
  browse_root: string
  project_root: string
  workspaces: WorkspacePreset[]
}

export interface DirEntry {
  name: string
  path: string
}

export interface BrowseResult {
  browse_root: string
  path: string
  relative: string
  parent: string | null
  dirs: DirEntry[]
  truncated: boolean
  hidden_count: number
  markers: string[]
}

export const EVENT_TYPES = [
  'task.created',
  'node.started',
  'node.finished',
  'assistant.message',
  'llm.token',
  'tool.started',
  'tool.finished',
  'budget.updated',
  'approval.required',
  'task.finished',
  'error',
] as const

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(detail?.detail ?? `HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

export async function createTask(
  task: string,
  workspace?: string,
  model?: string,
): Promise<string> {
  const body: Record<string, string> = { task }
  if (workspace) body.workspace = workspace
  if (model) body.model = model
  const response = await fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await json<{ task_id: string }>(response)
  return payload.task_id
}

/** 可选模型：无模型模式 + 服务端配置的候选。 */
export async function listModels(): Promise<ModelList> {
  return json<ModelList>(await fetch('/api/models'))
}

/** 目录选择器需要的预设与浏览范围。 */
export async function listPresets(): Promise<Presets> {
  return json<Presets>(await fetch('/api/presets'))
}

/** 逐层浏览目录（服务端限制在 browse_root 之内）。 */
export async function browseDirs(path?: string): Promise<BrowseResult> {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  return json<BrowseResult>(await fetch(`/api/fs/dirs${query}`))
}

export async function listTasks(): Promise<TaskSummary[]> {
  return json<TaskSummary[]>(await fetch('/api/tasks'))
}

export async function getTask(id: string): Promise<TaskSummary> {
  return json<TaskSummary>(await fetch(`/api/tasks/${id}`))
}

export async function getHealth(): Promise<{ status: string; model: string }> {
  return json<{ status: string; model: string }>(await fetch('/api/health'))
}

/**
 * 订阅任务事件流。
 *
 * 用原生 EventSource：本项目的流式端点是 GET，不需要自定义 header（Last-Event-ID
 * 由 EventSource 在断线重连时自动带上），因此无需引入额外依赖。
 */
export function subscribe(
  taskId: string,
  handlers: { onEvent: (event: TaskEvent) => void; onClose?: () => void },
): () => void {
  const source = new EventSource(`/api/tasks/${taskId}/events`)

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (raw) => {
      const event = JSON.parse((raw as MessageEvent).data) as TaskEvent
      handlers.onEvent(event)
      if (event.type === 'task.finished' || event.type === 'error') {
        source.close()
        handlers.onClose?.()
      }
    })
  }

  source.onerror = () => {
    source.close()
    handlers.onClose?.()
  }

  return () => source.close()
}
