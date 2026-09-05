# Razorpay Test Mode capture

## Capture summary

- Environment: Razorpay Test Mode
- Successful payments captured: 6
- Failed payment attempts captured: 8
- Payment Link flows exercised: 3
- Subscription flows: unavailable in the test account during capture
- Duplicate-event replay: passed

The failure count is higher than the original 5–6 target because the Razorpay
Test Mode bank simulator produced additional genuine declines before successful
retries. No observed records were removed to force the result toward the target.

## Storage and sanitization

The webhook receiver stores the verified provider payload in PostgreSQL before
any export. `scripts/export_razorpay_events.py` creates the committed samples in
`data/raw/razorpay/` and recursively redacts customer contact data, names,
addresses, notes, card identifiers, card-number metadata and token identifiers.

Each committed record retains the provider name, Test Mode environment,
Razorpay event identifier, sanitized provider payload, capture timestamp and a
`sanitized: true` marker. Webhook signatures, API credentials and webhook
secrets are not exported.

## Duplicate-event verification

A stored event was replayed with its existing `x-razorpay-event-id` and a valid
signature calculated for the replay body. The endpoint returned HTTP 200 with
`status: duplicate`. PostgreSQL still contained exactly one row with that event
identifier.

## Limitation

Subscription events were not exposed by the Razorpay Test Mode account used for
this capture. No subscription events or provider identifiers were fabricated.
Subscription cases must therefore be generated later as explicitly labelled
synthetic records.
