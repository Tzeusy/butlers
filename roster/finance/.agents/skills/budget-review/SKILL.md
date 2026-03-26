---
name: budget-review
description: Interactive skill for setting, adjusting, and analyzing budgets with spending forecasts and recommendations
version: 1.0.0
---

# Budget Review Skill

This skill provides an interactive workflow for setting and reviewing budgets, analyzing current spending against limits, and forecasting future budget compliance.

## Purpose

Help the user establish healthy spending limits, review progress, adjust budgets based on life changes, and understand spending trends relative to goals.

## Prerequisites

Before starting the budget review workflow:
1. User has spending history (at least 30 days of transaction data)
2. Baseline spending profiles can be calculated from history
3. Optional: User has prior budget configurations to review
4. User is available for interactive responses

## Budget Review Flow

### 1. Session Initialization

Ask the user what they want to accomplish:

```
Budget Review Workflow

What would you like to do today?
1. Create a new budget from scratch
2. Review and adjust existing budgets
3. Analyze spending against budgets
4. Set up custom budget rules
5. Forecast next month's budget
```

### 2. Create Budget from Scratch

If creating new budgets:

**Step 1: Analyze Current Spending**
- Use `spending_summary(last_30_days)` to calculate average spend per category
- Show the user a summary:

```
Your spending over the past 30 days:

Groceries: $180 (avg $6/day)
Dining: $210 (avg $7/day)
Entertainment: $80 (avg $2.67/day)
Transport: $120 (avg $4/day)
Subscriptions: $120 (fixed/month)
Utilities: $150 (avg $5/day)
Shopping: $200 (varies)
Other: $60

Total: $1,120/month
```

**Step 2: Suggest Budget Limits**
- Based on spending history, suggest reasonable limits:
  - Conservative (20% buffer): $216 groceries, $252 dining, $96 entertainment, etc.
  - Moderate (10% buffer): $198 groceries, $231 dining, $88 entertainment, etc.
  - Relaxed (5% buffer): $189 groceries, $220 dining, $84 entertainment, etc.

```
I recommend starting with a moderate budget (10% buffer above your average):

Groceries: $200/month
Dining: $240/month
Entertainment: $90/month
Transport: $130/month
Subscriptions: $120/month
Utilities: $165/month
Shopping: $220/month
Other: $70/month

Total: $1,235/month

Does this feel right? Or would you prefer:
• Conservative (more aggressive savings)
• Relaxed (more flexibility)
• Custom (set each category yourself)
```

**Step 3: Configure Budget**
- For each category, confirm or customize the amount
- Set alert thresholds (warn at 80%, alert at 100%)
- Configure frequency (monthly, weekly, annual)

### 3. Review Existing Budgets

If reviewing existing budgets:

**Step 1: Load Current Budgets**
- Use `budget_list()` to retrieve all configured budgets
- Show current spending against each budget

```
Current Budgets:

Groceries: $200/month
Current spend (30d): $180 (90%)
Status: On track ✅

Dining: $200/month
Current spend (30d): $165 (82%)
Status: Warning ⚠️ (approaching limit)

Subscriptions: $100/month
Current spend (30d): $127 (127%)
Status: Exceeded 🔴
```

**Step 2: Adjust Budgets**
For each budget, offer to adjust:
```
Subscriptions budget exceeded. Options:
1. Increase budget to $130/month
2. Keep at $100/month and reduce subscriptions
3. Skip adjustment (review next month)
```

**Step 3: Store Updates**
- Use `budget_set()` to update any changed limits
- Confirm changes:

```
Budget updated:
✅ Subscriptions: $100 → $130/month

Your new total budget: $1,245/month (+$30)
```

### 4. Analyze Spending vs. Budgets

Show detailed breakdown:

```
# Budget Performance (Last 30 Days)

🟢 ON TRACK (Spending < 80% of budget)
• Groceries: $180/$200 (90%)
• Transport: $120/$130 (92%)
• Utilities: $150/$165 (91%)

🟡 WARNING (80-99% of budget)
• Dining: $165/$200 (82%)
• Entertainment: $75/$90 (83%)

🔴 EXCEEDED (>100% of budget)
• Subscriptions: $127/$100 (127%)
• Shopping: $220/$200 (110%)

**Trends:**
• Dining trending up (+15% vs prior month)
• Subscriptions consistently over (4 months in a row)
• Transport under control (consistent 90% utilization)

**Recommendations:**
1. Address subscription overage — review for unused services
2. Monitor dining trend — may exceed budget next month
3. Investigate shopping spike — one-time purchase or pattern?
```

### 5. Forecast Next Month's Budget

Use recent trends to predict next month:

```
# Next Month Forecast (April 2026)

Based on your 3-month trend analysis:

Groceries: $185 (stable)
Dining: $180 (trending up +5%)
Entertainment: $85 (stable)
Transport: $125 (stable)
Subscriptions: $130 (after expected adjustment)
Utilities: $155 (seasonal reduction)
Shopping: $150 (normalizing after spike)
Other: $65 (stable)

**Predicted Total**: $1,175/month
**Projected Status**: On budget if trend continues

Suggestions:
• Increase Dining budget to $200 (allows for trending spending)
• Continue monitoring Shopping (spike may recur)
• Maintain Subscriptions at $130 (after cleanup)
```

### 6. Memory Storage

Store budget preferences and decisions:

```python
memory_store_fact(
    subject="user",
    predicate="budget_philosophy",
    content="prefers moderate budgets with 10% buffer above average spending",
    permanence="stable",
    importance=8.0,
    tags=["budget", "preference"]
)

memory_store_fact(
    subject="subscriptions",
    predicate="audit_frequency",
    content="user wants monthly audit to prevent overage",
    permanence="stable",
    importance=7.0,
    tags=["budget", "subscription", "frequency"]
)
```

### 7. Summary and Follow-Up

Recap the session:

```
# Budget Review Summary

**Actions Taken:**
✅ Reviewed 8 budget categories
✅ Updated subscriptions budget to $130/month
✅ Analyzed 3-month trend for forecasting
✅ Identified dining as risk area (trending up)

**Next Steps:**
1. Monitor dining spending (may need adjustment by April 15)
2. Complete subscription audit to reduce overage
3. Investigate shopping spike (recurring or one-time?)

**Next Review:** April 1, 2026 (monthly cadence)

Would you like to:
• Set a calendar reminder for next review
• Review specific categories in detail
• Adjust budgets further
• Export budget summary
```

## Error Handling

- If no spending history exists: "I need at least 30 days of transaction history to analyze spending patterns. Check back after adding more transactions."
- If budget configuration fails: "Could not update budget. Check the amount and category name."
- If forecast calculation fails: Skip forecast, show historical summary instead

## Example Scenarios

### Example 1: New User (No Prior Budgets)

```
User: "Help me set budgets for the first time"

Bot:
1. Analyzes 30 days of spending
2. Suggests categories and amounts
3. User confirms or customizes
4. Creates budgets in database
5. Sets calendar reminder for monthly review

Result: New user has 8 budgets configured within 5 minutes
```

### Example 2: Existing Budgets (Adjustment Review)

```
User: "Review my current budgets"

Bot:
1. Loads existing budgets
2. Shows current spending against each
3. Flags exceeded/warning categories
4. Offers adjustments
5. User confirms changes

Result: User updates 2 budgets based on life changes (roommate moved out)
```

### Example 3: Spending Analysis

```
User: "Am I on track with my budgets?"

Bot:
1. Calculates YTD spending by category
2. Shows % utilization of budget
3. Identifies trends (up/down)
4. Recommends preventive actions

Result: User sees dining trending up, decides to reduce next month
```

### Example 4: Forecast Planning

```
User: "What will I spend next month?"

Bot:
1. Analyzes 3-month trend
2. Adjusts for seasonal factors (heating in winter, travel in summer)
3. Predicts next month's budget
4. Suggests preventive adjustments

Result: User can pre-adjust budgets before overspending occurs
```

## Version History

- v1.0.0 (2026-03-26): Initial stub for interactive budget review and forecasting workflow
