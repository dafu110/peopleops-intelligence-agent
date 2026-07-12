# Product Evidence: Governed HRBP Co-pilot

## User Role

The primary user is an HRBP or recruiting operations specialist who needs to prepare evidence, coordinate follow-up work, and retain an auditable record. The product does not replace the HRBP's hiring judgment.

## Core Workflow

1. Import or paste a resume and a JD.
2. Review the candidate-assistance package: redacted evidence, missing information, source labels, and questions to validate.
3. The HRBP records whether the package was adopted or manually rewritten.
4. If follow-up is needed, the agent creates a draft rather than taking an external action.
5. The HRBP submits, approves or rejects the draft, then records execution or failure. Failed work can return to pending review.
6. Audit, task replay, citations, and aggregate metrics remain available in the console.

## Measures

| Measure | Definition | Boundary |
| --- | --- | --- |
| Agent adoption rate | Candidate-assistance adoption events divided by candidate-assistance tasks | Not a hiring-success metric |
| Human rewrite rate | Rewrite events divided by recorded adoption/rewrite feedback | Indicates review effort, not model quality alone |
| Approval duration | Mean elapsed time for terminal approval records | Uses workflow timestamps only |
| Citation open rate | Citation-open events divided by citation-shown events | Measures evidence engagement |
| Failure reasons | Aggregated task/tool error categories | No candidate text or PII is stored in metrics |

## Trade-offs

- The agent withholds employment recommendations even when evidence appears strong. This reduces automation but preserves HR accountability.
- Local mode records auditable drafts and artifacts; production connectors remain separately gated by identity, tenancy, and release evidence.
- Metrics are event-based and display `0` or no sample rather than fabricated performance claims.

## De-identified HRBP Trial Feedback

> "The evidence and missing-information sections made it easier to prepare a structured follow-up conversation. I still made the final decision myself, but the audit trail and draft approval step reduced handoff ambiguity."

This is a de-identified illustrative feedback record for product-review discussion, not a production customer claim.
