# Teacher Authoring

This context owns educator work-in-progress, offline model-bundle admission, generation provenance, and explicit approval without granting an AI model publication or grading authority.

## Language

**Authoring Draft**:
A mutable teacher workspace containing proposed learning or assessment material that has not entered a canonical published context.
_Avoid_: Lesson, question, generated content

**Model Bundle**:
A signed, versioned, locally cached package containing model weights, tokenizer, runtime contract, license evidence, hashes, and capability limits.
_Avoid_: AI model, downloaded weights

**Generation Record**:
Local provenance linking one generated proposal to its Model Bundle, bounded input references, configuration, safety checks, and teacher actions without storing unnecessary source content.
_Avoid_: Prompt log, AI history

**Teacher-Approved Draft**:
An Authoring Draft that a currently authorized educator explicitly reviewed and approved for submission to a named owning context.
_Avoid_: AI-approved, ready content

**Draft Disposition**:
The explicit approval, rejection, or abandonment outcome that ends an Authoring Draft's active lifecycle.
_Avoid_: Draft status, deletion, publish result

**Deterministic Authoring Template**:
A non-model workflow that preserves complete manual authoring on devices that cannot safely run an admitted Model Bundle.
_Avoid_: AI fallback, reduced feature

**Model Openness Claim**:
The exact statement of whether a Model Bundle provides permissively licensed open weights or independently satisfies the OSI Open Source AI Definition, supported by its training and release evidence.
_Avoid_: Open-source model, fully open AI

**AI Quality Campaign**:
A frozen, reviewer-controlled evaluation of one exact Model Bundle against representative pathology-teaching authoring tasks, sourced factual claims, prohibited actions, and safety boundaries.
_Avoid_: Prompt test, model benchmark

## Retention ceilings

- An Authoring Draft expires no later than 90 days after its Draft Disposition.
- A Generation Record expires no later than one year after the associated Draft Disposition.
