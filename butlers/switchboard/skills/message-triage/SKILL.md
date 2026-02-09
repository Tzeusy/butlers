---
name: message-triage
description: Classify and route incoming messages to specialist butlers with confidence scoring
trigger_patterns:
  - "classify this message"
  - "which butler should handle"
  - "route this to"
  - "triage incoming"
---

# Message Triage Skill

## Purpose
This skill helps you classify incoming messages and route them to the appropriate specialist butler. Use structured confidence scoring to determine whether to route immediately, ask for clarification, or default to the general butler.

## Available Butlers

### Relationship Butler
**Handles:** Contacts, interactions, relationships, social events, gifts, reminders about people

**Domain indicators:**
- Names of people (friends, family, colleagues)
- Social interactions (calls, meetings, dinners, hangouts)
- Important dates (birthdays, anniversaries)
- Gift tracking (ideas, purchases, giving)
- Relationship management (who knows whom, introductions)
- Contact information (phone numbers, addresses, email)
- Loans and money between people
- Groups and social circles

**Example messages:**
- "Add John's birthday on March 15th"
- "Remind me to call Mom next Tuesday"
- "Log that I met Sarah for coffee today"
- "Gift idea for Alice: new headphones"
- "What's Bob's email address?"

### Health Butler
**Handles:** Health measurements, medications, conditions, symptoms, diet, research

**Domain indicators:**
- Measurements (weight, blood pressure, glucose, temperature)
- Medications (prescriptions, dosing, adherence)
- Medical conditions (diagnoses, status updates)
- Symptoms (severity, duration, triggers)
- Meals and nutrition (food logging, calories, macros)
- Exercise and physical activity
- Health research and notes
- Medical appointments and tracking

**Example messages:**
- "Log my weight as 165 lbs"
- "I took my morning medication"
- "I have a headache, severity 6/10"
- "Log breakfast: oatmeal with berries"
- "Track blood pressure 120/80"

### General Butler
**Handles:** Freeform data, notes, lists, tasks, anything not fitting specialist domains

**Domain indicators:**
- TODO lists and tasks
- Notes and memos
- Ideas and brainstorming
- Project tracking
- Generic data storage
- Anything ambiguous or multi-domain
- Fallback for unclear intent

**Example messages:**
- "Add milk to shopping list"
- "Note: meeting went well today"
- "Create a reading list"
- "Remember to renew passport"
- "Store this recipe"

## Classification Framework

### Step 1: Identify Domain Signals
Scan the message for domain-specific keywords and concepts:

**Relationship signals:** person names, relationships (friend/family/colleague), social verbs (call/meet/visit), gifts, birthdays, contacts

**Health signals:** body measurements, medical terms, symptoms, medications, food/meals, exercise, doctor/medical

**General signals:** lists, tasks, notes, reminders without people/health context, abstract ideas

### Step 2: Score Confidence
Use this three-tier system:

**HIGH confidence (>80%):**
- Clear single-domain match
- Multiple strong domain signals
- No conflicting indicators
- **Action:** Route immediately to specialist butler

**MEDIUM confidence (40-80%):**
- Weak domain signals or ambiguous phrasing
- Could fit multiple domains
- Context suggests specialist but not certain
- **Action:** Route to best-match butler with acknowledgment of uncertainty

**LOW confidence (<40%):**
- No clear domain signals
- Highly ambiguous or multi-domain
- Insufficient context to classify
- **Action:** Default to general butler (catch-all)

### Step 3: Handle Edge Cases

**Multi-domain messages:**
When a message spans multiple domains, choose based on primary intent:
- "Remind me to take medication when I see Dr. Smith" → **health** (medication is primary, appointment context is secondary)
- "Log that I had dinner with John and I ate pasta" → **relationship** (social interaction is primary, meal detail is secondary)
- If truly balanced → **general** (let user be more specific later)

**Ambiguous messages:**
- "Remind me tomorrow" (no context) → **general**
- "How's Alice doing?" → **general** (could be relationship query or just note-taking)
- "Track this" (no details) → **general**

**Names without clear context:**
- "Schedule appointment with Dr. Johnson" → **health** (doctor context)
- "Schedule call with Johnson" → **relationship** (person-to-person)
- "Johnson delivered the package" → **general** (unclear, possibly just a note)

## Decision Matrix

| Message Type | Signals | Confidence | Route To |
|--------------|---------|------------|----------|
| Person's birthday | name + date | HIGH | relationship |
| Log medication | drug name + "take"/"log" | HIGH | health |
| Shopping list item | food/item + "list" | HIGH | general |
| "Call Mom" | name + social verb | HIGH | relationship |
| "Weight: 150" | number + health measurement | HIGH | health |
| "Remind me to..." (no context) | task verb only | LOW | general |
| "Had lunch with Sarah" | name + meal | MEDIUM | relationship |
| "Ate salad" | meal only | MEDIUM | health |
| "Sarah is on medication" | name + health | MEDIUM | general |

## Output Format

When using this skill, structure your classification as:

```
Butler: <butler_name>
Confidence: <high|medium|low>
Reasoning: <brief explanation>
```

Example:
```
Butler: relationship
Confidence: high
Reasoning: Message contains person name "John" and social interaction verb "met". Clear relationship domain match.
```

## Routing Actions

After classification:

1. **HIGH confidence:** Call the route tool immediately with target butler and tool name
2. **MEDIUM confidence:** Call route tool but acknowledge uncertainty in response
3. **LOW confidence:** Route to general butler or ask user for clarification if message is too vague

## Progressive Disclosure

**Quick start:** Look for person names → relationship, health terms → health, everything else → general

**Detailed:** Use the confidence scoring framework above

**Expert:** Consider context, user patterns, and edge cases to refine classification over time
