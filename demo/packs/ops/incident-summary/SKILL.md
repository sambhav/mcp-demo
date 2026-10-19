---
name: incident-summary
description: Turn incident notes, logs or a chat transcript into a blameless incident summary. Use after an outage or when asked to write a postmortem.
---

# Incident summary

Produce, in this order:

1. **Summary**: what broke, who was affected, for how long (one paragraph).
2. **Timeline**: UTC timestamps, detection → mitigation → resolution.
3. **Root cause**: the technical cause, and the conditions that let it happen.
4. **What went well / what didn't**.
5. **Action items**: owner placeholder, priority, each one preventing recurrence or speeding detection.

Blameless: describe systems and decisions, never individuals.
