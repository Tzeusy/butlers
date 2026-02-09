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
This skill helps you classify incoming messages and route them to the appropriate specialist butler. Use structured confidence scoring to determine whether to route immediately, ask for clarification, or default to the general butler. For multi-domain messages, decompose into self-contained sub-prompts.

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
- If truly balanced → decompose into sub-prompts (see below)

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

---

## Decomposition Decision Tree

When a message arrives, follow this decision tree:

```
1. Does the message have ONE clear domain?
   YES → Route entire message to that butler
   NO → Continue to step 2

2. Does the message span MULTIPLE domains with clear boundaries?
   YES → Decompose into sub-prompts (one per butler)
   NO → Continue to step 3

3. Is the intent ambiguous or unclear?
   YES → Route to general butler (default)
   NO → Re-evaluate from step 1
```

### When NOT to Decompose

Do NOT decompose in these cases:

1. **Single domain**: The message clearly belongs to one specialist butler
2. **Unclear boundaries**: You cannot clearly separate concerns between domains
3. **Ambiguous intent**: The user's intent is unclear or requires clarification
4. **Interdependent actions**: The actions require cross-butler coordination that decomposition would break

In these cases, route to the most appropriate single butler or default to general.

## Multi-Domain Decomposition

When decomposing, create self-contained sub-prompts for each butler. Each sub-prompt must:

1. Include all necessary context from the original message
2. Be executable independently without cross-references
3. Preserve entity names, relationships, and temporal information
4. Use clear, actionable language

### Context Preservation Guidelines

When splitting a message, ensure critical context travels with each sub-prompt:

- **Named entities**: "Mom", "Dr. Smith", "Lisa" → Include in relevant sub-prompt
- **Relationships**: "my brother", "my doctor" → Preserve the relationship context
- **Temporal info**: "Tuesday", "next week", "at 3pm" → Include in time-sensitive sub-prompts
- **Quantities**: "150mg", "3 miles", "twice daily" → Keep units with the action
- **Implicit context**: If the user says "call Mom Tuesday and log weight", the relationship sub-prompt needs "Mom" (not just "call Tuesday")

## Decomposition Examples

### Example 1: Health + Relationship

**Input Message:**
> "Remind me to take my blood pressure meds at 8am daily, and text my sister to check on her recovery"

**Decomposition:**

```json
[
  {
    "butler": "health",
    "prompt": "Set up a daily reminder at 8am to take blood pressure medication"
  },
  {
    "butler": "relationship",
    "prompt": "Send a text message to my sister to check on her recovery"
  }
]
```

**Rationale:** Clear separation between health (medication reminder) and relationship (contacting sister). Each sub-prompt is self-contained.

### Example 2: Relationship + Health + General

**Input Message:**
> "Schedule a dinner with Mom next Friday, log my weight as 185 lbs, and remind me to backup my computer this weekend"

**Decomposition:**

```json
[
  {
    "butler": "relationship",
    "prompt": "Schedule a dinner with Mom next Friday"
  },
  {
    "butler": "health",
    "prompt": "Log weight measurement: 185 lbs"
  },
  {
    "butler": "general",
    "prompt": "Set a reminder to backup computer this weekend"
  }
]
```

**Rationale:** Three distinct domains with clear boundaries. Context preserved: "Mom" in relationship prompt, "185 lbs" in health prompt, "this weekend" in general prompt.

### Example 3: Complex Multi-Domain with Context

**Input Message:**
> "My doctor recommended I start taking Metformin 500mg twice daily, call Mom on Tuesday to tell her about the new prescription, and set up a monthly check-in with Dr. Chen starting next month"

**Decomposition:**

```json
[
  {
    "butler": "health",
    "prompt": "Add new medication: Metformin 500mg, to be taken twice daily, as recommended by doctor"
  },
  {
    "butler": "relationship",
    "prompt": "Call Mom on Tuesday to tell her about the new Metformin prescription"
  },
  {
    "butler": "relationship",
    "prompt": "Set up a monthly recurring check-in with Dr. Chen, starting next month"
  }
]
```

**Rationale:** Medical information goes to health butler. Two relationship actions: calling Mom (with prescription context preserved) and scheduling with Dr. Chen. Each sub-prompt includes the specific context needed (medication name, person names, timing).

### Example 4: Single Domain (No Decomposition)

**Input Message:**
> "Add a reminder to send birthday gifts to Mom, Dad, and Lisa before December, and log that I sent flowers to Aunt Jane last week"

**No Decomposition - Route to relationship:**

This is entirely about relationship management (gifts, interactions with people). Even though there are multiple actions, they all belong to the same domain and should be handled together by the relationship butler.

### Example 5: Ambiguous (No Decomposition)

**Input Message:**
> "I need to do something about my energy levels"

**No Decomposition - Route to general:**

Intent is unclear. Could be health-related (medication, diet, sleep), could be lifestyle (exercise, schedule), or could be seeking advice. Route to general butler to clarify intent before involving specialists.

## Implementation Notes

- Use the Switchboard's MCP tools to route messages to target butlers
- Log all decomposition decisions for audit trail
- If a butler returns an error, log it but continue processing other sub-prompts
- Aggregate responses from multiple butlers before returning to the user

## Progressive Disclosure

**Quick start:** Look for person names → relationship, health terms → health, everything else → general

**Detailed:** Use the confidence scoring framework above

**Expert:** Consider context, user patterns, decomposition for multi-domain messages, and edge cases to refine classification over time
