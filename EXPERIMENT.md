# Vasooli Evaluation Protocol

## Objective

Evaluate whether Vasooli can detect revenue at risk, diagnose the likely
cause, select a bounded recovery action, execute or simulate that action,
and measure confirmed recovered revenue across a fixed batch.

## Frozen dataset design

- Total cases: 300
- Dataset-generation seed: 42
- Outcome-simulation seed: 2026
- Development cases: 240
- Held-out cases: 60
- Split ratio: 80/20
- Currency: INR
- Monetary values are stored in paise.
- No records will be removed or reselected after results are observed.

## Case distribution

| Case type | Count |
|---|---:|
| Successful/control payment | 105 |
| Failed one-time payment | 60 |
| Abandoned checkout | 45 |
| Failed subscription | 40 |
| Overdue B2B invoice | 30 |
| Promise-to-pay | 20 |
| Total | 300 |

## Failure distribution

The following values are scenario-design assumptions, not claims about
Indian payment-industry base rates.

| Failure reason | Weight |
|---|---:|
| Insufficient funds | 30 |
| Issuer declined | 20 |
| Bank timeout | 15 |
| Authentication failed | 10 |
| Expired card | 10 |
| Mandate revoked | 7 |
| Technical error | 5 |
| Blocked/suspicious | 3 |

## Required difficult cases

The batch must include:

- Successful control cases
- Opted-out customers
- Missing contact consent
- Already-refunded orders
- Cancelled orders
- Duplicate webhooks
- Out-of-order events
- Already-paid cases
- Revoked mandates
- Disputed invoices
- Invalid contact details
- Failed recovery attempts
- Kept promises
- Broken promises
- Ambiguous cases requiring human review

## Provenance labels

Every relevant field must be assigned one of:

- RAZORPAY_TEST
- SYNTHETIC
- DERIVED
- LLM_INFERRED
- SIMULATED_OUTCOME

Original Razorpay Test Mode fields must not be overwritten.

## Primary metrics

### Total-pool revenue recovery rate

confirmed recovered amount / total at-risk amount

### Attempted revenue recovery rate

confirmed recovered amount / eligible attempted amount

### Case recovery rate

confirmed recovered cases / attempted cases

## Counting rules

A case is not recovered merely because:

- A reminder was sent
- A payment link was opened
- A retry was scheduled
- A voice call was answered
- A promise-to-pay was obtained

Revenue is counted as recovered only after a confirmed test-mode payment
or a clearly labelled simulated confirmed-payment outcome.

## Evaluation procedure

1. Generate the complete batch.
2. Validate the complete batch.
3. Split the batch before policy tuning.
4. Record the held-out SHA-256 checksum.
5. Use only development cases during implementation.
6. Freeze policies, prompts and outcome assumptions.
7. Process the held-out cases once.
8. Publish successful, unsuccessful, blocked and escalated outcomes.

## Held-out lock

- Held-out cases: 60
- Canonical SHA-256: `bda35fe8d6cf4a0eb5fd0f2b08ad1354454bd4ed3d6e18fc8813ab3f146517e6`
- Dataset-generation commit: pending until the locked dataset commit is created
- Checksum method: JSON keys sorted, compact separators, UTF-8 encoded

The checksum is calculated from canonical JSON. Therefore, `shasum -a 256`
on the formatted file may produce a different value without indicating that
the dataset contents changed.
