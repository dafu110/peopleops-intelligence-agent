# PeopleOps Candidate Assistance Agent Spec

## Goal and Scope

The agent helps HRBP staff organize policy evidence, resume/JD evidence, missing information, and governed follow-up actions. It is a co-pilot, not an employment decision maker.

It must not recommend hiring, rejection, ranking, compensation, or any final candidate disposition. A named HRBP remains accountable for every employment decision and every externally visible action.

## Actions and Gates

| Action | Purpose | Reversible | Gate |
| --- | --- | --- | --- |
| Policy retrieval | Return cited internal-policy evidence | Yes | None |
| Candidate assistance | Surface redacted evidence and review questions | Yes | HRBP review required |
| Create action draft | Prepare an interview or stage-change request | Yes | HRBP submits draft |
| Approve or reject action | Decide whether a prepared action may proceed | Partly | HRBP with `tool` permission |
| Execute approved action | Mark the local reference action executed | Compensatable where supported | Approved record and `tool` permission |

## Control Loop

1. Classify the request as policy Q&A, candidate assistance, or governed action.
2. Create a bounded plan and stop after one answer, evidence package, or tool attempt.
3. Redact PII before model prompts, audit events, and operator metrics.
4. For candidate assistance, return only evidence, missing information, and HRBP review guidance.
5. For actions, move through `DRAFT -> PENDING -> APPROVED/REJECTED -> EXECUTED/FAILED`; only `FAILED -> PENDING` can retry.

## Guardrails and Escalation

- Stop and request missing resume/JD material rather than infer candidate history.
- Remove decision-language from candidate-assistance output and label it for HRBP review.
- Treat uploaded documents and model output as untrusted data; no model output can directly invoke an unrestricted action.
- Require human review for any action draft and capture state transitions in the audit chain.
- Escalate unavailable evidence, conflicting material, repeated failure, or any decision request to an HRBP.

## Evaluation

- Candidate safety gate: PII redaction, decision-language removal, cited source labels, and missing-material refusal.
- Agent trace gate: intent, bounded plan, and permitted tool checks.
- RAG gate: answer coverage, citations, and PII leakage checks.
- Operations metrics: adoption, human rewrite, approval duration, citation open rate, and aggregated failure reasons.

## Failure Handling

The safe default is to stop and ask for clarification. A failed approval can return to `PENDING` for a new review; no rejected or executed approval can be replayed automatically.
