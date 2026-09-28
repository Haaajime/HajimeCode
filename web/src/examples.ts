/**
 * 默认任务场景。
 *
 * 约定：
 * - `task` 是**完整文本**，一点即整段填入输入框，界面上不再截断显示。
 * - `workspaceKey` 对应 `/api/presets` 返回的工作区 key，点击时会顺带把工作目录切过去，
 *   这样"子文件夹场景"才能真正在对应目录里跑起来。留空表示沿用当前选择的目录。
 */

export interface ExampleTask {
  /** 场景短标签（仅用于识别，不是任务内容） */
  label: string
  /** 完整任务文本 */
  task: string
  workspaceKey?: string
}

export interface ExampleGroup {
  title: string
  hint: string
  items: ExampleTask[]
}

export const EXAMPLE_GROUPS: ExampleGroup[] = [
  {
    title: '当前仓库',
    hint: '在 Hajime2Code 自己身上跑 —— 这些是最贴近真实开发的场景',
    items: [
      {
        label: '结构统计',
        task: '统计 src 下的 Python 文件数量，并说明目录结构',
        workspaceKey: 'project',
      },
      {
        label: '定位再读',
        task: '项目里定义了哪些 `@tool`？分别在哪个文件的哪一行？请先用内容搜索定位，再读取确认。',
        workspaceKey: 'project',
      },
      {
        label: '总结定位',
        task: '读 README.md 并总结这个项目是做什么的、和 HajimeCode 是什么关系',
        workspaceKey: 'project',
      },
      {
        label: '测试覆盖',
        task: 'tests 目录下一共有多少条测试？哪个文件的测试最多？',
        workspaceKey: 'project',
      },
    ],
  },
  {
    title: '样例仓库 · 读取覆盖度',
    hint: '专门用来验证「能不能读全」——含隐藏文件、二进制、符号链接、非 ASCII 路径',
    items: [
      {
        label: '全量枚举',
        task: '列出这个项目里全部的文件和目录（包括所有子目录、隐藏文件），给出完整清单和每类文件的数量',
        workspaceKey: 'sample_repo',
      },
      {
        label: '哪些读不了',
        task: '仓库里哪些文件不应该按文本读取？哪些路径是非 ASCII 或含空格的？为什么读取它们容易出问题？',
        workspaceKey: 'sample_repo',
      },
      {
        label: '符号链接',
        task: '仓库里有没有符号链接？分别指向哪里？读取它们时会发生什么？',
        workspaceKey: 'sample_repo',
      },
    ],
  },
  {
    title: '样例仓库 · 子文件夹场景',
    hint: '各个子目录单独作为工作区 —— 用来验证"把工作区指到子目录"这条路径是否正常',
    items: [
      {
        label: 'src/core',
        task: '读取这个目录下的所有文件，说明 engine.py 和 models.py 的关系，以及 Config 是怎么被用上的',
        workspaceKey: 'sample_src_core',
      },
      {
        label: 'src/utils',
        task: '这个目录里定义了哪些函数？它们在仓库其他地方被调用了吗？',
        workspaceKey: 'sample_src_utils',
      },
      {
        label: '深嵌套',
        task: '从当前工作区出发，说明它处于原仓库的哪一层？每一层各有什么内容？',
        workspaceKey: 'sample_deep',
      },
      {
        label: '非 ASCII 路径',
        task: '当前目录名是非 ASCII 的，请列出其中的文件并读取内容，确认工具能正确处理这类路径',
        workspaceKey: 'sample_cjk',
      },
      {
        label: '含空格路径',
        task: '当前目录名里含有空格，请列出它的内容并读取其中的文件，确认路径能正确处理',
        workspaceKey: 'sample_spaces',
      },
    ],
  },
]
