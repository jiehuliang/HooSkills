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
4. **Related Reading Detection** — scan `<skill-dir>/reading-notes/` INDEX.md files, detect and load related past readings
5. **Phase 2: Q&A Interaction** — user asks questions about the content; answer with precise citations
6. **Phase 3: Summary & Export** — wrap-up synthesis connecting all concepts; export to `<skill-dir>/reading-notes/`

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
- **关键要点详细讲解**: for each key concept/technique/mechanism identified, provide in-depth explanation covering: (1) what it is, (2) how it works concretely, (3) why it's used here (design rationale / problem it solves), (4) its relationship to alternative approaches. This is NOT a one-line definition — unpack the concept so someone unfamiliar can understand it fully without consulting external sources. Prioritize concepts that are: novel to non-experts, central to understanding the document, or easily misunderstood if only glossed over
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

#### 6. Related Readings

After completing the reading notes, scan `<skill-dir>/reading-notes/` for past saved notes that relate to the current document. This is done by searching all `INDEX.md` files (Tier 0, already in context if previously loaded).

**Relevance Detection**: Compare the current document against each INDEX.md using these dimensions (weighted):

| Match | Weight | Signal |
|-------|--------|--------|
| `domain` overlap | 3 pts | Same field (e.g. both "视频编码") |
| `techniques` overlap | 3 pts | Same methods (e.g. both use ConvLSTM) |
| `problem` similarity | 2 pts | Same or adjacent problem |
| `key_concepts` overlap | 2 pts | Shared concepts or terminology |
| `one_liner` semantic match | 1 pt | Similar core idea |

**Scoring thresholds** (保守策略 — 宁缺毋滥):
- **≥5 pts → 强关联**: Auto-load the related note's README.md + insights.md summary. Present a comparison paragraph.
- **3-4 pts → 中关联**: Mention the related note with its one_liner. Offer to load details.
- **<3 pts → 不提及**: Skip to avoid noise.

**Output**: List the top 10 results in a "Related Readings" subsection:

```
### Related Readings

**强关联**:
- [Doc Title 1] — 同属 <domain> 领域，共用 <techniques> 技术。核心差异：<difference>。

**中关联**:
- [Doc Title 2] — 都涉及 <problem>。说"展开"加载完整对比。

**无历史关联** (if no matches found): 不提此板块。
```

**Cross-Document Loading Rules**:
- 强关联时：自动加载 README.md（摘要级对比），不加载完整 chapters/
- 用户追问时：加载 insights.md + 相关 chapters/ 做深度对比
- Phase 2 中用户问"和之前读的 XX 有什么关系" → 精确匹配并加载完整笔记

**Context Budget**: INDEX.md per note ≈ 200 tokens. Assume 30 saved notes → ~6000 tokens for all INDEX files. Strong-related auto-loads add ~800 tokens each (max 3). Total worst case ~8400 tokens — acceptable.

### Quality Constraints

All Phase 1 output must satisfy these three rules. They are non-negotiable — every section is subject to them.

#### 1. 禁止空洞评价 (No Vague Praise)

Statements like "该设计很优雅"、"实验很充分"、"该方案很有效" are forbidden. Every evaluative claim MUST be backed by concrete specifics:

| 禁止 (Forbidden) | 正确 (Correct) |
|---|---|
| "该设计很优雅" | "该设计通过二值化瓶颈将压缩率控制从手工调参变为通道数选择，减少了一个需要搜索的超参" |
| "实验很充分" | "实验覆盖了3个数据集(Vimeo-90K, UVG, 19个自选序列)、4个基线(DAC, DISCOVER, DeepVC, LDVC)、2个指标(PSNR, MS-SSIM)" |
| "性能提升显著" | "在低运动序列上PSNR比DAC高2-5dB，在高运动序列上高0.5-1.5dB" |

If the document itself uses vague language, note it: "该文仅声称'效果良好'，未给出具体数据支撑"。

#### 2. 跨章节交叉验证 (Cross-Section Verification)

When the same concept, claim, or data point appears across multiple sections, verify consistency:

- A claim in Introduction that is later contradicted by actual results → flag it
- A parameter described as X in Methods but used as Y in Experiments → flag it
- A limitation mentioned in Discussion that was glossed over in Conclusion → flag it

Add a **一致性检查** note to the Cross-Document Insights section when discrepancies are found. When everything is consistent, a brief "各章节对 <核心声明> 的描述一致" suffices.

#### 3. 缺失信息标记 (Missing Information Markers)

When the document omits key information that a competent reader would expect, mark it explicitly. Use this format:

> ⚠️ **信息缺失**: <what is missing, why it matters>

Typical triggers:
- Training hyperparameters not reported (learning rate, batch size, optimizer)
- Dataset composition not detailed (train/val/test split, class balance)
- Key assumptions not stated explicitly
- Baselines not justified (why these baselines, why not others)
- Error bars / variance not reported
- Computational cost not disclosed
- Failure cases not shown

Missing information is NOT a flaw in the reading — it's a signal about the document's completeness. Note it and move on.

### End of Phase 1

After outputting all notes, transition to Phase 2 with the warm-up Q&A:
- "深读完成。以下是几个值得探讨的问题，你可以从中选择或提出自己的问题（说'总结'进入总结环节）："
- "Deep read complete. Here are a few questions worth exploring — pick one or ask your own (say 'summarize' to wrap up):"

---

## Phase 2: Q&A Interaction

### Answer Format

- Direct, precise answer first, then context
- Citations to specific sections/chapters in the source
- When a question spans multiple sections, trace the connections
- If the question reveals a gap in the reading, load the relevant passage and supplement
- Gently correct misunderstandings by citing the original text

### Cross-Document Q&A

When the user asks about relationships to past readings:

- "和之前读的 XX 比呢" / "这个和 YY 有什么关系" → Load the related note's README.md + insights.md (Tier 1). If user drills deeper, load specific chapters.
- "这个技术和之前 Z 里的技术有什么不同" → Load technique descriptions from both documents' chapters, compare side by side.
- If the user doesn't specify which past note → list the top related ones from the Related Readings output and ask which to compare.

### Q&A Warm-up

When entering Phase 2, proactively provide **2-3 example questions** worth exploring. These should be non-trivial — not "what is X" but why, how, trade-offs, or implications. Present as a menu:

> **你可以从以下问题开始提问（或提出你自己的问题）：**
> 1. <Question 1>
> 2. <Question 2>
> 3. <Question 3>

### Question Tagging

Tag every user question with a category label before answering, so the user can see what dimension they're exploring and which dimensions remain untouched:

| 标签 | 适用场景 |
|------|---------|
| 🔍 概念澄清 | "X和Y的区别是什么"、"这个术语什么意思" |
| ⚙️ 机制深挖 | "为什么这样设计"、"具体怎么实现的" |
| 🧪 实验评估 | 数据集选择、基线对比、指标可信度 |
| 🔗 跨域延伸 | "这个思路能否用到Z领域"、"与另一篇工作的关系" |
| 🧭 批判审视 | "局限性在哪"、"假设是否合理"、"有没有更好的方案" |

Show the tag at the top of each answer. Periodically review the conversation's tag coverage — if a dimension hasn't been touched, suggest it: "目前还没聊到实验评估，想了解论文的数据集和基线选择是否公允吗？"

### Progressive Deepening

Structure follow-ups in three tiers. After answering, guide the user toward the next tier if they haven't reached it yet:

- **第一层 查漏 (Fill Gaps)**: Answer the literal question. Ensure foundational understanding is solid.
- **第二层 机制深挖 (Mechanism)**: Nudge toward "为什么这样设计"、"内部怎么运作的"、"各组件怎么配合"
- **第三层 批判延伸 (Critique & Extend)**: Nudge toward "局限在哪"、"假设被打破会怎样"、"能迁移到其他场景吗"、"这篇工作之后的方向是什么"

After each answer, if the user hasn't reached the next tier, offer a nudge:

> *想继续往下挖吗？比如 [下一层的具体追问]*

Don't force progression — if the user says "够了" or changes topic, adapt naturally.

### Follow-Up Prompting

After answering, always offer 1-2 natural follow-up questions that deepen the current topic. These should feel organic, not mechanical:

> **延伸思考**：<1-2 specific follow-up questions tied to what was just discussed>

### Cross-Turn Knowledge Accumulation

When answering a new question, explicitly reference prior Q&A turns when relevant. This builds the sense of cumulative understanding:

> 结合你之前问的 <prior topic>，这里的 X 恰好解释了为什么 Y...

### Depth Control

At the end of each answer, offer the user a compact set of options to control direction:

> 想继续了解：[1] 更深入 [2] 与其他方法对比 [3] 实践/实验细节 [4] 换个话题

Track Q&A pairs that produce genuine insight — include in the final export.

User can exit Q&A phase by saying "总结" / "summarize" / "done" / "好了".

---

## Phase 3: Summary & Export

### Wrap-up Summary

Present a cohesive synthesis:

**关键要点串联**: Start by listing each key concept/technique/mechanism from the document in a logical flow, briefly summarizing what each is and why it matters. Then connect them — show how they form a chain: A enables B, B feeds into C, C addresses the problem stated at the beginning. This should read as a coherent narrative, not a bullet list.

**原则**:
- Each key point: one sentence summary, one sentence on its role in the bigger picture
- The connection between adjacent points must be explicit ("X does Y, which then serves as input to Z")
- Skip trivial details; only keep the load-bearing concepts
- The reader should walk away understanding the document's core argument as a causal chain

- Tie the entire document together — how concepts relate and depend on each other
- Highlight the overall design philosophy, argument structure, or main contribution
- For papers: final assessment of contribution quality, methodology, and limitations
- For RFCs: key normative requirements at a glance
- Note open questions from both the reading and the Q&A phase
- If strong-related readings exist, add a **跨文档连接** paragraph: how this document extends, contradicts, or complements past readings

### Export (Mandatory)

Notes are always exported — INDEX.md is required for future cross-document relevance detection in the knowledge graph. After presenting the summary, export automatically without asking:

1. Generate all files based on the full reading session (Phase 1 + Phase 2 Q&A)
2. Create directory structure in one pass
3. Announce: "笔记已输出到 `reading-notes/<name>/`，包含 N 个章节笔记和 M 条问答。下次阅读时将自动检测关联。"

Follow `output-format.md` for file templates and directory structure. **INDEX.md is mandatory** — fill all frontmatter fields accurately.

If directory exists, save to `<name>-v2/` (auto-increment).

#### Output Constraints

**位置约束 (Location)**:
- Must write to `<skill-dir>/reading-notes/<doc-name>/` — this is the deep-reading skill's own directory (where SKILL.md lives), NOT the project root. This keeps the knowledge graph self-contained and portable
- `reading-notes/` lives inside the skill directory; if it doesn't exist, create it
- `<doc-name>` follows naming convention in `output-format.md`

**内容约束 (Content)**:
- INDEX.md: all 6 frontmatter fields (`title`, `domain`, `techniques`, `problem`, `key_concepts`, `related_to`, `one_liner`) must be filled. No empty fields, no placeholder values
- Each file generated must contain substantive content (no empty files, no "TBD" placeholders)
- Chapter files must cover ALL sections of the original document — no skipped sections
- insights.md must include cross-document connections if any were found during Related Reading Detection

**关联完整性约束 (Graph Integrity)**:
- If Related Reading Detection found strong/moderate matches, those connections must be recorded in both `insights.md` (current doc) AND the related doc's `insights.md` (update the `跨文档关联` section)
- This keeps the knowledge graph bidirectional — if A links to B, B should also know about A

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
