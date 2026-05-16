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

全自动深度阅读，三阶段流程：自动深读 → 交互问答 → 总结导出。支持渐进式知识图谱，自动检测与历史笔记的关联。

**三阶段流程：**

| 阶段 | 内容 |
|------|------|
| **Phase 1 自动深读** | 文档概览 → 结构地图 → 逐章精读/略读 → 关键要点详细讲解 → 跨章节洞察 → 关联历史笔记 |
| **Phase 2 交互问答** | 热身问题 → 分类标记（概念/机制/实验/延伸/批判）→ 三层递进引导 → 追问提示 → 深度控制 |
| **Phase 3 总结导出** | 关键要点串联（因果链）→ 跨文档连接 → 导出到渐进式加载目录 |

**Phase 1 质量约束：**
- 禁止空洞评价（"设计优雅""实验充分"）— 必须用具体数据/细节支撑
- 跨章节交叉验证 — 同一概念在不同章节的说法是否一致
- 缺失信息标记 — 未报告的超参、数据集划分、误差条等显式标记 `⚠️`

**Phase 2 交互增强：**
- 问题分类标记（🔍概念澄清 / ⚙️机制深挖 / 🧪实验评估 / 🔗跨域延伸 / 🧭批判审视）
- 三层递进引导（查漏 → 机制深挖 → 批判延伸）
- 跨轮知识累积 — 新回答显式引用之前的讨论
- 深度控制开关 — `[1] 更深入 [2] 对比 [3] 实验细节 [4] 换话题`

**渐进式知识图谱：**

导出笔记按 4 级分层加载：
- **Tier 0** — `INDEX.md`（始终在上下文，~200 tokens），含 frontmatter 元数据用于关联检测
- **Tier 1** — `README.md` + `insights.md`（检测到关联时自动加载）
- **Tier 2** — `structure.md` + `questions.md`（用户要求时加载）
- **Tier 3** — `chapters/`（按需单章加载）

读新文档时自动扫描所有历史 INDEX.md，按 `domain + techniques + problem + key_concepts` 加权计算关联度，强关联自动加载、中关联提示可展开、弱/无关不提。宁缺毋滥，最多取 top 10。

**支持输入：** 本地 PDF / Markdown / URL（Playwright 优先）/ 粘贴文本

**支持文档类型：** RFC / 学术论文 / 代码重技术文档 / 书籍 / 博客

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
