# Output Format

Templates for auto-generating reading notes after Phase 3 summary and export.

## Directory Structure (Progressive Loading Tiers)

Tier 0 = always in context (minimal tokens). Tier 1 = loaded on relevance hit. Tier 2+ = loaded on demand.

```
reading-notes/
  <document-name>/
    INDEX.md           # Tier 0 · Always loaded (~200 tokens)
    README.md          # Tier 1 · Loaded when related reading triggered
    insights.md        # Tier 1 · Cross-document connections
    structure.md       # Tier 2 · Loaded on explicit user request
    questions.md       # Tier 2 · Significant Q&A only
    chapters/          # Tier 3 · Per-chapter, loaded on demand
      01-<chapter>.md
      02-<chapter>.md
```

## Naming Convention

- `<document-name>`: lowercase, hyphens for spaces, no special chars
  - "RFC 9113" → `rfc-9113`
  - "Designing Data-Intensive Applications Ch.5" → `designing-data-intensive-applications-ch5`
  - "Attention Is All You Need" → `attention-is-all-you-need`
- Chapter files: zero-padded number + short name from heading
- If directory exists, auto-increment: `rfc-9113-v2`, `rfc-9113-v3`, etc.

## INDEX.md Template (Tier 0)

This is the minimal "always loaded" file that enables cross-document relevance detection. Keep under 300 words.

```markdown
---
title: <exact document title>
domain: [<primary field>, <secondary field>]
techniques: [<technique 1>, <technique 2>, <technique 3>]
problem: <one-line problem statement>
key_concepts: [<concept 1>, <concept 2>, <concept 3>]
related_to: [<reference frame, competitor, predecessor work>]
one_liner: <core thesis in one sentence>
---
```

**Field Guidelines**:
- `domain`: Primary research/application area. Use broad, well-known categories (e.g. "视频编码", "分布式系统", "NLP").
- `techniques`: Specific methods/algorithms/architectures used. This is the strongest relevance signal.
- `problem`: What problem does this work solve? One sentence.
- `key_concepts`: Novel or distinctive concepts introduced. Not generic terms.
- `related_to`: What prior work, standards, or approaches does this relate to?
- `one_liner`: The core insight or main result. This is the fallback relevance signal.

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

## 关键要点详细讲解

### <Key Point 1>

**是什么**：<one-sentence definition>
**怎么工作**：<concrete mechanism, step by step>
**为什么用在这里**：<design rationale, problem it solves>
**与替代方案的关系**：<comparison to alternatives, why this choice>

### <Key Point 2>

**是什么**：<definition>
**怎么工作**：<mechanism>
**为什么用在这里**：<rationale>
**与替代方案的关系**：<comparison>

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

## 跨文档关联

- 与 [Related Doc 1](path) 的关系：<connection type — extends/contradicts/complements>
- 与 [Related Doc 2](path) 的关系：<connection type>

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

Export is mandatory — INDEX.md is required for the knowledge graph. After Phase 3 summary, export automatically without asking:

1. Create directory structure in one pass
2. Generate all files based on the full reading session (Phase 1 + Phase 2 Q&A)
3. INDEX.md is mandatory — fill all frontmatter fields accurately
4. Announce: "笔记已输出到 `reading-notes/<name>/`，包含 N 个章节笔记和 M 条问答。下次阅读时将自动检测关联。"
5. If directory exists, save to `<name>-v2/` (auto-increment) to avoid overwriting

## Output Constraints

### Location

- Always write to `<skill-dir>/reading-notes/<doc-name>/` — the skill's own directory, not the project root
- Never output to arbitrary paths or the project root
- Create `reading-notes/` inside the skill directory if it doesn't exist

### Content

- INDEX.md: all 6 frontmatter fields required, no empty values, no placeholders
- Every file must contain substantive content — no empty files, no "TBD"
- Chapter files cover every section of the original document — no skipped sections
- insights.md records cross-document connections from Related Reading Detection

### Graph Integrity

- When Related Reading Detection finds strong/moderate matches, update BOTH docs:
  - Current doc's `insights.md` → add `跨文档关联` entries
  - Related doc's `insights.md` → add reciprocal `跨文档关联` entry
- This ensures the knowledge graph is bidirectional
