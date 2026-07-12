# ADR 0003: Candidate Assistance Is Evidence-Only

## Status

Accepted.

## Context

Resume/JD matching can influence employment outcomes and may contain PII or biased signals. A numeric fit score or an unbounded language-model response can be mistaken for a hiring decision.

## Decision

Candidate assistance returns only redacted, source-labeled evidence, missing information, and HRBP review guidance. The UI and workflow must not produce a hire/reject recommendation. Follow-up actions begin as drafts and require explicit state transitions with audit records.

## Consequences

- HRBP staff retain final decision authority.
- Candidate-safety evaluations block PII leakage, decision-language output, absent-source presentation, and missing-material hallucination.
- Adoption metrics describe operator interaction, not employment outcomes.
- External hiring-system execution remains out of scope until production identity, document authorization, and connector evidence are available.
