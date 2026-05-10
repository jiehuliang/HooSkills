# HooSkills

个人 Skills 集合。

## 快速开始

放到Agent对应的skill目录中，Agent 会自动发现可用的 Skills。

## Skills 目录

| Skill | 描述 | 触发场景 |
|-------|------|----------|
| [deep-reading](skills/deep-reading/) | 系统化的深度阅读辅助，支持长文档、PDF、RFC 的结构化阅读与笔记导出 | 提供文档/URL/PDF 要求阅读、总结、精读时自动触发 |
| [job-switch-planner](skills/job-switch-planner/) | 技术岗跳槽规划，覆盖用户画像、市场调研、岗位分析到跳槽计划的完整流程 | 用户说"我想跳槽"、"帮我分析该往哪个方向走"时自动触发 |

### deep-reading

系统化的阅读辅助 Skill，帮助 AI 引导用户高效阅读长文档、PDF、书籍和技术规范。

**工作流：** 输入文档 → 策略选择 → 背景概览 → 结构地图 + 精读推荐 → 交互阅读 → 总结串联 → 导出笔记

**交互模式：**
- **逐段引导** — "逐段带我读"，逐段解读等待确认
- **按需深入**（默认）— 选择章节编号深入阅读
- **问题驱动** — 直接提问，定位相关段落回答

**支持输入：** 本地 PDF / Markdown / URL（Playwright 优先） / 粘贴文本

### job-switch-planner

技术岗跳槽规划 Skill，引导用户完成从自我认知到落地的完整 7 阶段流程。

**7 阶段管线：** CP1 用户画像 → CP2 期望收集 → CP3 公众评价 → CP4 前景分析 → CP5 岗位确定 → CP6 招聘信息采集 → CP7 跳槽计划

**交互模式：**
- **对话引导** — 逐阶段引导用户输入，关键节点展示分析结果
- **检查点回退** — 可随时回退到任意阶段修改参数，后续自动重新计算
- **信息采集** — 通过 OpenCLI 自动化采集知乎、Boss直聘、V2EX 等平台数据

**支持输入：** 简历文本 / 对话问答 / 手动粘贴的招聘信息

## 手动安装

将 `skills/` 下的 Skill 目录复制或软链接到 opencode 的全局 Skills 目录：

```bash
# 全局目录
ln -sf $(pwd)/skills/* ~/.config/opencode/skills/

# 或项目级目录
ln -sf $(pwd)/skills/deep-reading /path/to/project/.opencode/skills/deep-reading
```

## 添加新 Skill

1. 在 `skills/` 下创建 `<skill-name>/SKILL.md`
2. `SKILL.md` 必须包含 YAML frontmatter：`name`（目录名一致）、`description`
3. 在本 README 的 Skills 目录表格中新增一行
4. 运行 `bash setup.sh` 安装

## 命名规则

- 小写字母、数字、单连字符分隔
- 长度 1-64 字符
- 不能以连字符开头或结尾
- 不能包含连续 `--`

## 许可

MIT
