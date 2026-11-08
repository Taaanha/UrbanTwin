"""Rules and wording for City Accountability.

The module flags documentation gaps and unusually fast recurrence for
independent review. It never concludes why something happened and never
alleges wrongdoing by any person or organisation.
"""

PROJECT_STATUSES = ("approved", "in_progress", "completed", "cancelled")
INSPECTION_OUTCOMES = ("meets_specification", "partially_meets", "does_not_meet", "inconclusive")

# Lab thresholds, editable here. They are screening rules, not legal tests.
RECURRENCE_RADIUS_M = 40.0
FAST_RECURRENCE_DAYS = 90
BUDGET_OVERRUN_PCT = 0.10

DISCLAIMER = (
    "Flags below are screening signals for independent review. They show gaps or "
    "unusual patterns in the records. They are not findings of fault, and they do "
    "not allege wrongdoing by any contractor, official or organisation."
)

CONTEXT_LIMITATIONS = (
    "Rainfall data (for example CHIRPS) is not loaded in this lab, so weather "
    "context cannot be checked. OSM drainage may be incomplete. Materials, "
    "traffic load and subgrade are not recorded. Many causes can produce early "
    "recurrence."
)
