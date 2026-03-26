---
name: anomaly-triage
description: Interactive skill for investigating, classifying, and resolving detected spending anomalies
version: 1.0.0
---

# Anomaly Triage Skill

This skill provides an interactive workflow for reviewing detected anomalies, understanding their context, and taking action (mark as fraud, dispute, add to allowlist, etc.).

## Purpose

Help users investigate suspicious transactions, classify them as legitimate or fraudulent, and maintain an anomaly allowlist to reduce false positives over time.

## Prerequisites

Before starting the anomaly triage workflow:
1. An anomaly digest has been run and anomalies are available via `anomaly_scan()`
2. Transaction details are retrievable via `list_transactions()` or `get_transaction()`
3. Merchant allowlist and blocklist are maintained (optional)
4. User is available for interactive responses

## Anomaly Triage Flow

### 1. Session Initialization

Show user pending anomalies:

```
🔍 Anomaly Triage Workflow

You have 5 anomalies pending review:
1. ⚠️ Duplicate charge: DoorDash $42.50 (2 charges, 1 hour apart)
2. 🚨 High-risk merchant: CryptoBridge $500
3. 📈 Spending spike: Dining $127.50 (3x your daily average)
4. 🆕 New merchant: FarmerMarketDowntown $34.20
5. 💰 Subscription price change: Spotify $9.99 → $12.99

Which would you like to investigate?
[1 / 2 / 3 / 4 / 5 / review all / skip all]
```

### 2. Anomaly Investigation

For each anomaly, show details and guide user through classification:

#### Type: Duplicate Charge

```
🔍 INVESTIGATING: Duplicate DoorDash Charges

Transaction 1:
- Merchant: DoorDash
- Amount: $42.50
- Time: 2026-03-26 18:35
- Order ID: #ORD-5847392

Transaction 2:
- Merchant: DoorDash
- Amount: $42.50
- Time: 2026-03-26 18:36 (1 minute later)
- Order ID: #ORD-5847392 (same order!)

Classification: **Likely duplicate charge** (same order, same amount, within minutes)

Actions:
1. ✅ Mark both as duplicate (recommend refund request)
2. 📧 Flag for manual review with DoorDash
3. 💾 Mark first one as correct, second as error
4. ❓ More info / Cancel
```

#### Type: High-Risk Merchant

```
🔍 INVESTIGATING: CryptoBridge $500

Transaction:
- Merchant: CryptoBridge
- Amount: $500.00
- Category: Detected as "Cryptocurrency"
- Time: 2026-03-26 14:20
- Account: Chase Credit Card ending in 4532

Risk Factors:
⚠️ High-risk category (cryptocurrency/gambling)
⚠️ Large amount ($500 — 10x your typical category spend)
⚠️ New merchant (not in your history)

Your typical spending in this category: $0/month (never)

Actions:
1. ✅ This is legitimate — I made this transaction
2. 🚫 This is fraud — I did NOT make this transaction
3. ❓ I'm not sure — tell me more
4. 🔍 Show recent similar transactions
5. ❓ Cancel
```

#### Type: Spending Spike

```
🔍 INVESTIGATING: Dining Spike $127.50

Transaction:
- Merchant: OaklandFineTableRestaurant
- Amount: $127.50
- Time: 2026-03-26 20:15
- Card: Amex

Your Baseline:
- Typical dining spend: $45/day
- Today's spend: $127.50 (283% above average)
- This month's average: $6.50/transaction

Context:
⚠️ Significantly above your daily average
⚠️ Weekend dinner (higher spend expected)
✅ Legitimate high-end restaurant

Actions:
1. ✅ This is legitimate — special occasion / group dinner
2. 🚫 This is fraud — I did NOT make this transaction
3. 💾 Add OaklandFineTableRestaurant to allowlist (for future)
4. 📊 Show all dining transactions this month
5. ❓ Cancel
```

#### Type: New Merchant

```
🔍 INVESTIGATING: FarmerMarketDowntown $34.20

Transaction:
- Merchant: FarmerMarketDowntown
- Amount: $34.20
- Category: Groceries (inferred)
- Time: 2026-03-26 10:30
- Location: Oakland, CA

Analysis:
✅ Amount reasonable for groceries
✅ Time of day is typical for shopping
✅ Category matches likely user behavior
⚠️ First time seeing this merchant

Actions:
1. ✅ This is legitimate — I shopped here
2. 🚫 This is fraud — I did NOT make this transaction
3. 💾 Add to allowlist (won't flag similar future transactions)
4. 🏪 Show other grocery transactions today
5. ❓ Cancel
```

#### Type: Price Change

```
🔍 INVESTIGATING: Spotify Price Increase

Subscription:
- Service: Spotify
- Previous amount: $9.99/month
- New amount: $12.99/month
- Change: +$3.00 (+30%)
- Renewal date: 2026-04-03

Context:
⚠️ Significant price increase (30%)
ℹ️ Spotify announced price increase on 2026-03-15

Actions:
1. ✅ Keep subscription — worth the cost
2. 🚫 Cancel subscription — too expensive
3. ❓ I need more time to decide
4. 💾 Add Spotify to price-watch list
5. ❓ Cancel
```

### 3. Action Resolution

After user responds, confirm and apply action:

**Duplicate Mark:**
```
Confirmed: Both transactions marked as duplicate
✅ Request refund from DoorDash for $42.50
✅ Remove one transaction from tracked spending
💾 Stored in dispute log for follow-up

Next step: Contact DoorDash support with these transaction IDs
```

**Fraud Report:**
```
Confirmed: Transaction marked as FRAUD
🚨 Recommend immediate action:
1. Contact your card issuer immediately
2. Request dispute/chargeback on $500 charge
3. Monitor account for similar suspicious activity

Would you like me to:
• Create a reminder to follow up with bank
• Run a security scan for other suspicious transactions
• Add CryptoBridge to your fraud blocklist
```

**Allowlist Addition:**
```
Confirmed: FarmerMarketDowntown added to allowlist
✅ Future transactions from this merchant won't trigger anomaly alerts
💾 Stored in your known merchants list

This helps me learn your genuine spending patterns.
```

**Subscription Cancellation:**
```
Confirmed: Spotify cancellation requested
⚠️ Important: Manual action required
You'll need to:
1. Visit Spotify.com and log in
2. Navigate to Account > Subscription
3. Select "Cancel Subscription"
4. Confirm cancellation

I can set a reminder for this if you'd like.

Estimated savings: $12.99/month
```

### 4. Anomaly Summary

After triaging all anomalies:

```
# Anomaly Triage Summary

**Processed**: 5 anomalies
**Legitimate**: 3 (allowlisted for future)
**Disputed/Fraud**: 1 (marked for chargeback)
**Needs Decision**: 1 (price change — user pending decision)

**Actions Taken:**
✅ Marked 2 DoorDash charges as duplicate
✅ Reported $500 crypto transaction as fraud
✅ Allowlisted FarmerMarketDowntown
⏳ Pending user decision on Spotify price increase

**Follow-up:**
1. Dispute DoorDash refund (contact support 2026-03-27)
2. File chargeback with Chase for $500 crypto fraud
3. Remind about Spotify cancellation deadline (2026-04-03)

**Next Review**: Next anomaly digest (tomorrow at 9pm)
```

### 5. Memory Storage

Store triage decisions:

```python
memory_store_fact(
    subject="FarmerMarketDowntown",
    predicate="allowlisted_merchant",
    content="legitimate grocery store — user shopping frequency ~2x/month",
    permanence="stable",
    importance=6.0,
    tags=["merchant", "allowlist", "groceries"]
)

memory_store_fact(
    subject="CryptoBridge",
    predicate="fraud_report",
    content="unauthorized $500 charge on 2026-03-26 — user disputed",
    permanence="volatile",
    importance=9.0,
    tags=["fraud", "dispute", "chargeback"]
)

memory_store_fact(
    subject="user",
    predicate="fraud_alert",
    content="unauthorized crypto transaction — monitor for similar activity",
    permanence="volatile",
    importance=8.0,
    tags=["security", "fraud", "alert"]
)
```

## Error Handling

- If anomaly data is unavailable: "No pending anomalies to review. Check back after the next anomaly digest runs."
- If transaction lookup fails: Show basic info available, skip detailed context
- If allowlist update fails: "Could not update allowlist. Try again later."
- If fraud reporting fails: "Could not mark as fraud. Contact your card issuer directly."

## Example Workflows

### Example 1: Duplicate Charge Resolution

```
User identifies: DoorDash charged twice
Bot investigates: Same order ID, same amount, 1 minute apart
User confirms: "Yes, only one order"
Bot marks: Duplicate, recommends refund request
User: "Can you contact them?"
Bot: "Manual step required — I'll set a reminder for tomorrow"
Result: Refund request initiated, saved $42.50
```

### Example 2: Fraud Detection and Dispute

```
Bot detects: $500 CryptoBridge (new merchant, high-risk)
User confirms: "I did NOT make this transaction"
Bot marks: FRAUD, initiates dispute logging
Bot offers: "Contact Chase immediately"
User: "I'll call them now"
Bot: "Set reminder to follow up on dispute in 5 days?"
Result: Chargeback filed, account protected
```

### Example 3: Legitimate But Unusual

```
Bot flags: $127.50 dining (3x average)
User explains: "Group dinner for friend's birthday"
Bot offers: "Add to allowlist to avoid future false alerts?"
User: "Yes, that helps"
Bot: "Allowlisted. High-spend dining won't flag again"
Result: Fewer false positives, better anomaly detection accuracy
```

## Version History

- v1.0.0 (2026-03-26): Initial stub for interactive anomaly investigation and resolution
