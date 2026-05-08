# Deep Reading Guide

Reference for identifying which sections of a document deserve careful, slow reading.

## Evaluation Dimensions

### 1. Information Density

High-value indicators:
- Core definitions and terminology introductions
- Algorithm or protocol state machine descriptions
- Key design decisions and trade-offs
- Constraints, invariants, preconditions
- Counter-intuitive conclusions or surprising results
- Normative requirements (MUST/SHALL in RFCs)

### 2. Goal Relevance

When user has declared a learning goal, prioritize:
- Passages that directly answer the user's goal
- Prerequisites needed to understand the goal topic
- Boundary conditions and edge cases related to the goal
- Cross-references that connect to the goal from other sections

### 3. Comprehension Difficulty

Indicators of sections that need slow reading:
- Nested abstractions (concept built on concept)
- Easily misread phrasing or ambiguous language
- Dense derivations with implicit assumptions
- Sections where skimming would produce wrong mental model

## Scoring

Rate each dimension: ★ (low) / ★★ (medium) / ★★★ (high)

A section is recommended for deep reading if:
- Any single dimension is ★★★, OR
- Two or more dimensions are ★★

## Recommendation Format

For each recommended section:

```
### [Section identifier — chapter number, heading, or page range]
- 推荐理由：[One sentence explaining WHY this matters for understanding the whole]
- 维度：信息密度 ★★☆ | 目标相关 ★★★ | 难度 ★★☆
- 建议方式：[Concrete reading strategy — e.g., "draw the state diagram", "compare with X"]
```

## Skip/Skim Annotations

For sections NOT recommended for deep reading, briefly note why:
- "历史背景，了解即可" (historical context, awareness sufficient)
- "实现建议（非规范性），按需查阅" (implementation advice, non-normative)
- "与当前目标无关，可跳过" (unrelated to current goal)
- "前面章节的具体示例，理解概念后可略读" (examples of earlier concepts)

## Ordering Recommendations

Present recommendations in suggested reading order, which may differ from document order:
1. Foundation sections (definitions, model) first
2. Core mechanism sections next
3. Edge cases and extensions last

If a later section is prerequisite to understanding an earlier one, note the dependency.
