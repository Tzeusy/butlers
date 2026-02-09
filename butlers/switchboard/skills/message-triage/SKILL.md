# Message Triage Skill

## Purpose

This skill enables the Switchboard butler to classify and route incoming messages to the appropriate specialist butler. It includes logic for handling both single-domain and multi-domain messages through decomposition.

## Core Routing Logic

### Available Butlers

- **relationship**: Manages contacts, interactions, reminders, gifts
- **health**: Tracks medications, measurements, conditions, symptoms
- **general**: Catch-all for anything that doesn't fit a specialist

### Basic Classification Rules

- If the message is about a person, contact, relationship, gift, or social interaction → relationship
- If the message is about health, medication, symptoms, exercise, or diet → health
- If unsure or the message is general → general

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

## Tool Usage

This skill uses:
- `route_message(butler_name, message)` - Route a message to a specific butler
- `log_session(details)` - Log decomposition decisions and routing outcomes
