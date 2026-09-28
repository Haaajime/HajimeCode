import { useCallback, useEffect, useState } from 'react'

import { browseDirs } from '../api'
import type { BrowseResult, WorkspacePreset } from '../api'

interface Props {
  value: string
  presets: WorkspacePreset[]
  onChange: (path: string) => void
}

/**
 * 工作目录选择器：既可直接填路径，也可在服务端限定的范围内逐层浏览。
 *
 * 浏览范围由服务端 `browse_root` 约束 —— 越界会被后端拒绝，前端不做安全判断。
 */
export function WorkspacePicker({ value, presets, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [browsed, setBrowsed] = useState<BrowseResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const go = useCallback(async (path?: string) => {
    setLoading(true)
    setError(null)
    try {
      setBrowsed(await browseDirs(path))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open && !browsed) void go()
  }, [open, browsed, go])

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between gap-2">
        <label className="text-[11px] text-slate-500">工作目录</label>
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400
                     transition hover:border-slate-500 hover:text-slate-200"
        >
          {open ? '收起浏览' : '浏览…'}
        </button>
      </div>

      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="留空用服务端默认工作区"
        className="mono mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2
                   text-xs text-slate-300 outline-none placeholder:text-slate-600 focus:border-sky-600"
      />

      {presets.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {presets.map((preset) => {
            const active = preset.path === value
            return (
              <button
                key={preset.key}
                type="button"
                title={preset.path}
                onClick={() => onChange(preset.path)}
                className={`rounded border px-1.5 py-0.5 text-[10px] transition ${
                  active
                    ? 'border-sky-700 bg-sky-950/50 text-sky-200'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {preset.label}
              </button>
            )
          })}
        </div>
      )}

      {open && (
        <div className="mt-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          {error && (
            <p className="mb-2 rounded bg-rose-950/60 px-2 py-1 text-[11px] text-rose-300">
              {error}
            </p>
          )}

          {browsed && (
            <>
              <div className="mb-1.5 flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={browsed.parent === null || loading}
                  onClick={() => void go(browsed.parent ?? undefined)}
                  className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400
                             transition hover:border-slate-500 hover:text-slate-200
                             disabled:cursor-not-allowed disabled:opacity-40"
                >
                  ↑ 上级
                </button>
                <span className="mono truncate text-[10px] text-slate-500" title={browsed.path}>
                  {browsed.relative === '.' ? browsed.browse_root : browsed.relative}
                </span>
              </div>

              <ul className="scroll-thin max-h-40 space-y-0.5 overflow-y-auto">
                {browsed.dirs.length === 0 && (
                  <li className="py-2 text-center text-[11px] text-slate-600">（没有子目录）</li>
                )}
                {browsed.dirs.map((entry) => (
                  <li key={entry.path}>
                    <button
                      type="button"
                      disabled={loading}
                      onClick={() => void go(entry.path)}
                      className="mono w-full truncate rounded px-1.5 py-1 text-left text-[11px]
                                 text-slate-400 transition hover:bg-slate-800/60 hover:text-slate-200"
                    >
                      {entry.name}/
                    </button>
                  </li>
                ))}
              </ul>

              <div className="mt-1.5 space-y-1 text-[10px] text-slate-500">
                {browsed.markers.length > 0 && (
                  <p>项目标记：{browsed.markers.join('、')}</p>
                )}
                {browsed.hidden_count > 0 && (
                  <p>已隐藏 {browsed.hidden_count} 个构建产物 / 隐藏目录（.git、node_modules 等）</p>
                )}
                {browsed.truncated && <p className="text-amber-400">子目录过多，列表已截断</p>}
              </div>

              <button
                type="button"
                onClick={() => {
                  onChange(browsed.path)
                  setOpen(false)
                }}
                className="mt-2 w-full rounded bg-sky-700 px-2 py-1 text-[11px] text-white
                           transition hover:bg-sky-600"
              >
                使用此目录
              </button>
            </>
          )}

          {loading && !browsed && <p className="py-2 text-center text-[11px] text-slate-600">加载中…</p>}
        </div>
      )}
    </div>
  )
}
