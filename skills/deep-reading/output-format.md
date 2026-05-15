# Output Format

Templates for auto-generating reading notes after Phase 3 summary and export.

## Directory Structure

```
reading-notes/
  <document-name>/
    README.md          # Overview: metadata, summary, key takeaways
    structure.md       # Full document structure with depth indicators
    chapters/
      01-<chapter>.md  # Per-chapter deep reading notes
      02-<chapter>.md
    insights.md        # Cross-chapter insights, connections, synthesis
    questions.md       # Selected Q&A from Phase 2
```

## Naming Convention

- `<document-name>`: lowercase, hyphens for spaces, no special chars
  - "RFC 9113" → `rfc-9113`
  - "Designing Data-Intensive Applications Ch.5" → `designing-data-intensive-applications-ch5`
  - "Attention Is All You Need" → `attention-is-all-you-need`
- Chapter files: zero-padded number + short name from heading
- If directory exists, auto-increment: `rfc-9113-v2`, `rfc-9113-v3`, etc.

## README.md Template

```markdown
# <Document Title>

- 来源：<file path or URL>
- 类型：<RFC / 论文 / 书籍 / 技术文档 / 博客>
- 阅读日期：<YYYY-MM-DD>
- 阅读目标：<user's stated goal, or "通读了解" if none>

## 一句话总结

<Core thesis in 1-2 sentences>

## 关键收获

- <Takeaway 1>
- <Takeaway 2>
- <Takeaway 3>

## 章节概览

| 章节 | 深度 | 要点 |
|------|------|------|
| <Chapter 1> | 精读/略读 | <one-line summary> |
| <Chapter 2> | 精读/略读 | <one-line summary> |
```

## structure.md Template

```markdown
# 文档结构

<Full chapter/section tree with depth indicators>

- 1. Introduction [精读]
  - 1.1 Background [略读]
  - 1.2 Contributions [精读]
- 2. Core Mechanism [精读]
  ...
```

## chapters/NN-name.md Template

```markdown
# <Chapter/Section Title>

## 核心内容

<What this chapter says, 3-5 sentences>

## 关键概念

- **<Concept A>**：<explanation>
- **<Concept B>**：<explanation>

## 重要细节

<Deep reading notes — non-obvious details, constraints, edge cases, design rationale>

## 与其他章节的关联

<How this connects to other parts of the document>
```

## insights.md Template

```markdown
# 阅读洞察

## 跨章节关联

- <Insight about how concepts connect across chapters>

## 整体架构/论证结构

<Overarching design philosophy or argument structure>

## 开放问题

- <Questions that remain after reading>

## 批判性思考（论文专用）

<Methodology assessment, assumption audit, limitation analysis>
```

## questions.md Template

```markdown
# 阅读问答记录

## Q: <User's question>

**A:** <Answer summary>

**相关段落：** <Location in source — chapter, section, page>

---

## Q: <User's question>

**A:** <Answer summary>

**相关段落：** <Location in source>

---
```

Only include Q&A pairs that produced genuine insight. Skip trivial clarifications.

## Export Behavior

1. After Phase 3 summary, ask user whether to export: "要我把笔记整理输出到 `reading-notes/<文档名>/` 吗？"
2. Only write files after user confirms
3. Create directory structure in one pass
4. Generate all files based on the full reading session (Phase 1 + Phase 2 Q&A)
5. Report what was created: "笔记已输出到 `reading-notes/<name>/`，包含 N 个章节笔记和 M 条问答。"
6. If directory exists, save to `<name>-v2/` (auto-increment) to avoid overwriting
