---
name: deep-reading
description: Use when user provides a document, PDF, URL, or technical spec (like RFC) to read, understand, summarize, or study in depth
---

# Reading

Systematic reading assistant for long documents, PDFs, books, and technical specs. Identifies sections worth deep reading, guides comprehension, and exports structured notes.

## Flow

1. **Receive input** — identify type (local file / URL / pasted text)
2. **Choose strategy** — based on document length
3. **Background & overview** — introduce context, usage scenarios, and high-level summary before any deep reading
4. **Output structure map** — chapter list + deep reading recommendations
5. **Interactive phase** — answer questions, guide reading
6. **Wrap-up summary** — tie the whole document together, connect key concepts across sections
7. **Export** — persist notes to `reading-notes/` when user finishes

## Input Handling

| Input | Action |
|-------|--------|
| Local PDF | Read tool with `pages` parameter for large files |
| Local Markdown/text | Read tool |
| URL | Playwright browser (preferred) — renders JS, preserves structure and formatting |
| URL (fallback) | If Playwright blocked, try WebFetch; if also blocked, download via curl then Read locally |
| Pasted text | Process directly |

For URLs, prefer Playwright because it renders the page as a user would see it, preserving tables, code formatting, and dynamic content. Fall back to simpler methods when blocked.

## Strategy Selection

- **Short document (<5000 words / <20 PDF pages):** Read fully → output overview + recommendations
- **Long document (≥5000 words):** Scan structure first → output structure map + recommendations → load sections on demand

### Structure Detection (long documents)

Priority order:
1. Explicit TOC / Table of Contents
2. Heading hierarchy (H1/H2/H3 or PDF bookmarks)
3. Section numbering patterns (e.g., "1. Introduction", "2. Terminology")
4. Fixed-length chunking with first-sentence summaries as fallback

## Overview Output (Required)

Every reading session starts with:

1. **Background & context** — what problem does this document address, why does it exist, what are the typical usage scenarios
2. **Metadata** — title, author, type, estimated length
3. **One-sentence summary**
4. **Structure map** — chapter/section list with deep-read markers
5. **Deep reading recommendations** — see deep-reading-guide.md for criteria
6. **Mode prompt** — "默认按需深入模式。你可以：选择章节编号深入 / 说'逐段带我读' / 直接提问"

The background section ensures readers have enough context to understand WHY the document matters before diving into HOW it works.

## Interaction Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| A: Guided | "逐段带我读" / "一段一段来" / "继续" / "下一段" | Read section by section, highlight key points, wait for confirmation |
| B: On-demand (default) | User picks a chapter/section number | Load and explain selected section |
| C: Question-driven | User asks a specific content question | Locate relevant passage, answer with context |

Mode switches automatically based on user intent. After answering a question in C mode, return to previous mode.

## Answering Guidelines

- Before diving into technical details, provide necessary background and usage scenarios so the reader understands WHY before HOW
- When explaining a section, always extract and highlight key points: core concepts, critical constraints, design decisions, and non-obvious implications
- Use tables, bullet lists, or bold text to make key points scannable
- Cite specific locations in the source text
- Load unread sections when a question requires them
- Gently correct misunderstandings, citing the original text
- Track key insights that emerge during discussion — include in final export

## Wrap-up Summary

When all recommended sections have been read, or when the user signals completion:
- Provide a cohesive summary that ties the entire document together
- Connect key concepts across sections, showing how they relate and depend on each other
- Highlight the overall design philosophy or architectural decisions
- Note any open questions or areas for further exploration
- Then ask if the user wants to export notes

## RFC-Specific Guidelines

When reading RFCs, apply additional practices from rfc-reading-guide.md to improve comprehension quality. Key areas: document identity check, requirement keywords (MUST/SHOULD/MAY) interpretation, cross-reference handling, ABNF reading, and security considerations.

## Export

When user says "阅读完了" / "总结一下" / "输出笔记" or similar:
- Ask for confirmation: "要我把笔记整理输出到 reading-notes/<文档名>/ 吗？"
- Follow output-format.md for directory structure and templates
- Do NOT write files during the reading phase
