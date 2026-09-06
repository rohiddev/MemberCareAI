# Member Claims Administrative Guide

## Claim Status

A claim status describes the current administrative processing state of a healthcare claim.

Common statuses may include:

- received
- processing
- paid
- denied

The actual status of a member's claim must come from the claims system of record.

## Billed Amount

The billed amount is the amount submitted by the healthcare provider.

It is not necessarily the amount the health plan recognizes for payment.

## Allowed Amount

The allowed amount is the amount recognized under applicable plan and provider arrangements for claim processing.

The actual allowed amount for a member's claim must come from the claims system of record.

## Plan Paid Amount

The plan-paid amount represents the amount paid by the health plan for the processed claim.

MemberCareAI must retrieve this value from the claim record and must not calculate or infer it from general policy documentation.

## Member Responsibility

Member responsibility is the amount assigned to the member as part of claim processing.

The actual amount must come from the member's claim record.

General deductible or coinsurance information must not be used to recalculate the member-responsibility amount.

## Security

Claim information is member-specific healthcare information.

A member must only receive details for claims they are authorized to access.