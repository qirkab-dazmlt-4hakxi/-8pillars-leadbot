from .db import due_reminders,mark_reminded
from .alerts import reminder

def run_reminders(now=None, send=True):
    due=due_reminders(now=now);processed=[]
    for r in due:
        # Mark after attempting notification. If no channels are configured, still record it so
        # local logs/API don't hammer the same reminder every 30 minutes.
        delivered=reminder(r) if send else False
        mark_reminded(r["id"],when=now)
        processed.append((r,delivered))
    return processed
