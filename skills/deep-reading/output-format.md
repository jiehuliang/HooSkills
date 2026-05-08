# Output Format

Templates and structure for persisting reading notes to disk.

## Directory Structure

```
reading-notes/
  <document-name>/
    README.md          # Overview: metadata, goal, summary, key takeaways
    structure.md       # Document structure map with deep-read markers
    chapters/
      01-<chapter>.md  # Per-chapter notes
      02-<chapter>.md
    insights.md        # Cross-chapter insights, connections, synthesis
    questions.md       # Selected Q&A from the reading session
```

## Naming Convention

- `<document-name>`: lowercase, hyphens for spaces, no special chars
  - "RFC 9113" → `rfc-9113`
  - "Designing Data-Intensive Applications Ch.5" → `designing-data-intensive-applications-ch5`
- Chapter files: zero-padded number + short name from heading

## README.md Template

```markdown
# <Document Title>

- 来源：<file path or URL>
- 类型：<RFC / 书籍 / 论文 / 技术文档 / 博客>
- 阅读日期：<YYYY-MM-DD>
- 阅读目标：<user's stated goal, or "通读了解" if none>

## 一句话总结

<Core thesis in 1-2 sentences>

## 关键收获

- <Takeaway 1>
- <Takeaway 2>
- <Takeaway 3>

## 精读章节

- <Chapter/Section>：<why it was worth deep reading>
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

<Deep reading notes — the non-obvious details, constraints, edge cases>

## 与其他章节的关联

<How this connects to other parts of the document, if applicable>
```

## insights.md Template

```markdown
# 阅读洞察

## 跨章节关联

- <Insight about how concepts connect across chapters>

## 个人理解

- <Synthesized understanding that goes beyond any single section>

## 开放问题

- <Questions that remain after reading>
```

## questions.md Template

```markdown
# 阅读问答记录

## Q: <User's question>

**A:** <Answer summary>

**相关段落：** <Location in source — chapter, section, page>

---
```

Only include questions that produced genuine insight. Skip trivial clarifications.

## Export Behavior

1. Ask user for confirmation before writing
2. Create directory structure in one pass
3. Generate all files based on the reading session
4. Report what was created: "笔记已输出到 `reading-notes/<name>/`，包含 N 个章节笔记"
5. Do NOT overwrite existing notes without asking — if directory exists, ask whether to merge or replace
