# Deep Reading Guide

Internal guide for Phase 1 auto deep read. Determines how deeply to process each section. Every section is read — this only controls depth of analysis.

## Depth Levels

- **精读 (Deep)**: Full extraction — every key point, constraint, and implication. For content the document cannot be understood without.
- **略读 (Light)**: Concise summary with key takeaways. For supporting content that enriches but isn't essential.

Every section gets at least 略读. No section is skipped.

## Evaluation Dimensions

### 1. Information Density

→ 精读:
- Core definitions and terminology introductions
- Algorithm or protocol state machine descriptions
- Key design decisions and trade-offs
- Constraints, invariants, preconditions
- Counter-intuitive conclusions or surprising results
- Normative requirements (MUST/SHALL in RFCs)

**关键要点详细讲解规则**: Every key concept, technique, or mechanism that appears in a 精读 section MUST receive in-depth explanation. This means:
- Do NOT stop at a one-sentence definition — unpack: what, how, why, and comparison to alternatives
- A reader unfamiliar with the domain should be able to understand the concept without external lookup
- Especially important for: domain-specific terminology, novel techniques, core algorithms, and concepts the document's argument depends on
- If a concept is used across multiple sections, the detailed explanation goes in the section where it's first introduced; later sections reference back

### 2. Goal Relevance

When user has declared a learning goal, → 精读:
- Passages that directly answer the user's goal
- Prerequisites needed to understand the goal topic
- Boundary conditions and edge cases related to the goal

### 3. Comprehension Difficulty

→ 精读 with extra explanation:
- Nested abstractions (concept built on concept)
- Easily misread phrasing or ambiguous language
- Dense derivations with implicit assumptions
- Sections where skimming would produce wrong mental model

### 4. Code Density

When code exceeds text:
- Extract architecture, data flow, and design rationale — not syntax
- Highlight: core algorithms, state transitions, API contracts
- Compress: imports, config boilerplate, trivial scaffolding
- If code and prose disagree, code is ground truth — flag this

### 5. Output Quality Constraints

Applied to every section regardless of depth level:

**No Vague Praise**: Evaluative claims like "elegant design", "thorough experiments", "effective approach" are banned. Every such claim must be replaced with concrete specifics (numbers, names, direct quotes from the source). If the document itself uses vague language, note it explicitly.

**Cross-Section Verification**: When a concept, claim, or data point appears in multiple sections, check that it's used consistently. Flag discrepancies: a parameter value that differs between Methods and Experiments, a claim in the Introduction contradicted by actual results, a limitation acknowledged in Discussion but erased in Conclusion.

**Missing Information Markers**: When key information a competent reader would expect is absent, mark it with `⚠️ 信息缺失`. Triggers include: missing hyperparameters, unreported data splits, unstated assumptions, unjustified baseline choices, absent error bars, undisclosed computational cost, failure cases not shown. This is not about the reading quality — it's about the document's completeness as a signal to the reader.

### 6. Cross-Document Relevance

When reading, actively note connections to previously saved reading notes. The INDEX.md files in `<skill-dir>/reading-notes/` serve as the knowledge base for this:

- **Technique lineage**: Is this technique an evolution of something seen before? A reaction against it?
- **Problem adjacency**: Is this paper solving the same problem from a different angle?
- **Contradiction**: Does this document's claim conflict with a past reading? Flag it.
- **Gap fill**: Does this answer an open question from a past reading?

The goal is to build cumulative understanding — every new reading should hook into the existing knowledge graph, not sit in isolation.

## Processing Priority (internal reading order)

May differ from document order:
1. Foundation sections (definitions, model) first
2. Core mechanism sections next
3. Edge cases, examples, extensions last

If a later section is prerequisite to understanding an earlier one, reorder accordingly.
