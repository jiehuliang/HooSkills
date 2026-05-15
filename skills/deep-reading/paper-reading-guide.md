# Paper Reading Guide

Internal guidelines for Phase 1 auto deep read of academic papers. The three-pass method is executed automatically and synthesized into the output. Q&A follows in Phase 2; summary and export in Phase 3.

## Paper Type Detection

Identify type early — each requires different focus:

| Type | Characteristics | Focus On |
|------|----------------|----------|
| 理论型 (Theoretical) | Lemmas, proofs, formal models | Assumptions, proof sketch, theorem implications |
| 系统型 (Systems) | Architecture diagrams, implementation, benchmarks | Design trade-offs, evaluation methodology |
| 实证型 (Empirical) | Experiments, statistical tests, datasets | Hypothesis, methodology, result validity |
| 综述 (Survey) | Taxonomy, literature comparison | Classification framework, research gaps |

## Three-Pass Method (Automatic)

Execute all three passes internally. Synthesize findings into the output notes.

### First Pass: Scout

Read: Title → Abstract → Conclusion → glance at References.

Extract:
- Problem category (theoretical / systems / empirical / survey)
- Core contribution: what's new? (new problem? new method? new insight?)
- Worth assessment: is this paper significant in its area?

### Second Pass: Understand

Read: Introduction (first/last paragraph) → Figures & Tables → Key Results → skim Methods → Related Work.

Extract:
- Assumptions the approach relies on
- Evaluation methodology and its convincingness
- Relationship to prior work
- Limitations the authors acknowledge

Do NOT read linearly. Focus on figures — they convey the main story.

### Third Pass: Deep Dive

Full reading, re-deriving, critiquing.

Extract:
- Can the argument/proof be reconstructed from the paper alone?
- Hidden assumptions or gaps
- What follow-up work does this enable?
- What would a competent reviewer criticize?

## Section-by-Section Processing

| Section | Processing |
|---------|-----------|
| Abstract | Extract problem, approach, key result |
| Introduction | Extract motivation, contributions list, paper roadmap |
| Related Work | Map how paper positions itself; note key references worth following |
| Background/Preliminaries | Extract definitions and notation; flag unfamiliar conventions |
| Method/Approach | Full deep read — the core contribution |
| Evaluation/Experiments | Extract setup, baselines, metrics, results; check validity |
| Discussion | Extract authors' interpretation; compare against actual data |
| Conclusion | Extract summary + future work claims |

## Critical Reading (always applied)

- **Claims vs. data**: Cross-check every claim against the actual results. Flag discrepancies.
- **Evaluation scrutiny**: Check for cherry-picked baselines, weak competitors, favorable metrics, missing error bars, train/test leakage.
- **Assumption audit**: List all assumptions. Note which are realistic and which are fragile.
- **Limitations**: The limitations section (or its absence) is a strong signal of paper quality.
- **Citation context**: Note whether this paper is foundational (widely cited positively) or controversial (has rebuttals).

## Common Pitfalls to Guard Against

| Pitfall | Guard |
|---------|-------|
| Reading linearly from start to finish | Use three-pass; most sections don't need equal depth |
| Getting stuck on unfamiliar notation | Note it, move on — notation often clarifies later |
| Accepting conclusions at face value | Always cross-check claims against methodology and data |
| Skipping Related Work | It positions the paper in the landscape; extract the taxonomy |
| Over-indexing on abstract | Abstracts are marketing; conclusions + figures tell the real story |
