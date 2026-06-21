"""Proactivity (P3): the scheduler + push delivery that let EDITH reach out first.

A background scheduler polls for due work (reminders now; calendar nudges later) and
delivers it to the user's registered devices through a :class:`~app.proactivity.push.PushSender`.
Push targets live in ``device_tokens``; scheduled nudges in ``reminders``.
"""
