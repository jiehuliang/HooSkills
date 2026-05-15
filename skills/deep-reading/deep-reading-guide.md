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

## Processing Priority (internal reading order)

May differ from document order:
1. Foundation sections (definitions, model) first
2. Core mechanism sections next
3. Edge cases, examples, extensions last

If a later section is prerequisite to understanding an earlier one, reorder accordingly.
