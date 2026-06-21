"""Third-party API integrations (OAuth relying-party flows + service clients).

Phase 2 wedge. The first integration is Google (Gmail read-only); Calendar and
Contacts reuse the same :class:`~app.integrations.google_oauth.GoogleOAuth` flow and
the encrypted ``provider_accounts`` token store.
"""
