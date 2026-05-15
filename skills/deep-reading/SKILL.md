---
name: deep-reading
description: Use when user provides a document, PDF, URL, or technical spec (like RFC) to read, understand, summarize, or study in depth
---

# Deep Reading

Fully automatic deep reading with post-read Q&A. Reads entire documents deeply in one pass, then opens an interactive Q&A phase, followed by summary and auto-export.

## Flow

1. **Receive input** — identify type (local file / URL / pasted text)
2. **Detect document type** — classify and choose specialized strategy
3. **Phase 1: Auto Deep Read** — load and deeply read the entire document; output comprehensive notes without asking
4. **Phase 2: Q&A Interaction** — user asks questions about the content; answer with precise citations
5. **Phase 3: Summary & Export** — wrap-up synthesis connecting all concepts; ask user whether to export to `reading-notes/`

## Input Handling

| Input | Action |
|-------|--------|
| Local PDF | Read tool with `pages` parameter for large files |
| Local Markdown/text | Read tool |
| URL | Playwright browser (preferred) — renders JS, preserves structure and formatting |
| URL (fallback) | If Playwright blocked, try WebFetch; if also blocked, download via curl then Read locally |
| Pasted text | Process directly |

For URLs, prefer Playwright because it renders the page as a user would see it, preserving tables, code formatting, and dynamic content. Fall back to simpler methods when blocked.

## Document Type Detection

After loading content, classify the document to choose the right strategy:

| Signature | Type | Specialized Guide |
|-----------|------|-------------------|
| "RFC" + 4-digit number, IETF stream markers | RFC | `rfc-reading-guide.md` |
| Abstract + Introduction + Related Work + (Method/Evaluation/Conclusion) | Academic Paper | `paper-reading-guide.md` |
| API references, code blocks > 30% of content | Code-heavy Tech Doc | Standard + code-density rules |
| Long chapters, narrative structure, TOC | Book | Standard |
| Short (<2000 words), informal, blog-style | Article/Blog | Standard |

## Strategy

- **Short document (<5000 words / <20 PDF pages):** Read fully in one pass
- **Long document (≥5000 words):** Read in chunks, processing each section deeply before moving to the next

Word count estimation for PDFs: `estimated_words ≈ pages × 400` (English) or `pages × 600` (Chinese).

### Structure Detection (long documents)

Priority order:
1. Explicit TOC / Table of Contents
2. Heading hierarchy (H1/H2/H3 or PDF bookmarks)
3. Section numbering patterns (e.g., "1. Introduction", "2. Terminology")
4. For papers: standard section names (Abstract, Introduction, Related Work, etc.)
5. Fixed-length chunking with first-sentence summaries as fallback

### Code-Heavy Documents

When code blocks exceed ~30% of total content:
- Focus on architecture, data flow, and design rationale — not line-by-line syntax
- Skip boilerplate: imports, configuration, trivial scaffolding
- Highlight: core algorithms, API contracts, state machines, error handling strategy
- Flag sections where the code and prose disagree (code is ground truth)

---

## Phase 1: Auto Deep Read

Read the entire document without asking the user what to read. Output all notes in one pass.

### Depth Levels (per section)

- **精读 (Deep)**: Full extraction — every key point, constraint, and implication. Used for high-density content (definitions, algorithms, design decisions, normative requirements).
- **略读 (Light)**: Concise summary with key takeaways. Used for supporting content (examples, background, boilerplate).

Every section gets at least 略读. See `deep-reading-guide.md` for evaluation criteria.

### Output Structure

Present the complete analysis:

#### 1. Document Overview
- **Metadata**: title, author, type, length, date
- **Background**: what problem this addresses, why it exists, typical usage scenarios
- **One-sentence summary**

#### 2. Structure Map
- Full chapter/section list with depth indicators (精读/略读)
- One-line annotation for each section

#### 3. Deep Reading Notes (per section)
For each section:
- **核心内容**: 3-5 sentence summary
- **关键概念**: definitions, terminology, important abstractions
- **重要细节**: constraints, edge cases, non-obvious implications, design rationale
- **关联**: how this section relates to others

#### 4. Cross-Document Insights
- How key concepts connect across sections
- Overarching design philosophy or argument structure
- Open questions or areas needing further exploration

#### 5. Type-Specific Analysis
- **RFC**: requirement keyword analysis (MUST/SHOULD/MAY with targets), security considerations, cross-reference map
- **Paper**: contribution assessment, methodology evaluation, limitations, three-pass synthesis
- **Code-heavy doc**: architecture overview, API surface summary, data flow

### End of Phase 1

After outputting all notes, transition to Phase 2:
- "深读完成。你可以就文档内容提问，或说'总结'进入总结环节。"
- "Deep read complete. Ask me anything about the document, or say 'summarize' to wrap up."

---

## Phase 2: Q&A Interaction

User asks questions about the document. Answer with:

- Direct, precise answer first, then context
- Citations to specific sections/chapters in the source
- When a question spans multiple sections, trace the connections
- If the question reveals a gap in the reading, load the relevant passage and supplement
- Gently correct misunderstandings by citing the original text

Track Q&A pairs that produce genuine insight — include in the final export.

User can exit Q&A phase by saying "总结" / "summarize" / "done" / "好了".

---

## Phase 3: Summary & Export

### Wrap-up Summary

Present a cohesive synthesis:
- Tie the entire document together — how concepts relate and depend on each other
- Highlight the overall design philosophy, argument structure, or main contribution
- For papers: final assessment of contribution quality, methodology, and limitations
- For RFCs: key normative requirements at a glance
- Note open questions from both the reading and the Q&A phase

### Export Prompt

After presenting the summary, ask the user:

- "要我把笔记整理输出到 `reading-notes/<文档名>/` 吗？"
- "Export notes to `reading-notes/<doc-name>/`?"

Wait for user confirmation before writing files.

### Export Structure

When user confirms:

```
reading-notes/
  <document-name>/
    README.md          # Overview + metadata + key takeaways
    structure.md       # Full structure map with depth indicators
    chapters/
      01-<chapter>.md  # Per-chapter deep reading notes
      02-<chapter>.md
    insights.md        # Cross-document connections and synthesis
    questions.md       # Selected Q&A from Phase 2
```

Follow `output-format.md` for file templates. If directory exists, save to `<name>-v2/` (auto-increment).

Report: "笔记已输出到 `reading-notes/<name>/`，包含 N 个章节笔记和 M 条问答。"

---

## RFC-Specific Guidelines

When reading RFCs, apply practices from `rfc-reading-guide.md`:
- Document identity check (stream, category, currency)
- Requirement keyword interpretation (MUST/SHOULD/MAY), including target identification (sender vs receiver)
- Cross-reference handling, ABNF translation, security considerations summary

## Paper-Specific Guidelines

When reading papers, execute the three-pass method automatically from `paper-reading-guide.md`:
- First pass: extract core contribution (problem, approach, key result)
- Second pass: evaluate methodology, results, and positioning
- Third pass: critique assumptions, gaps, and implications

Synthesize all three passes into the Phase 1 output.
