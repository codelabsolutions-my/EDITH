"""Google Contacts (People API) client + connector, and the scope→connector guard."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from app.connectors.base import ConnectorContext
from app.connectors.google_contacts import GoogleContactsConnector
from app.integrations.contacts_api import ContactsApi, ContactsApiError


def _api(handler) -> ContactsApi:
    return ContactsApi("access-token", transport=httpx.MockTransport(handler))


def _person(name: str, email: str, phone: str) -> dict:
    return {
        "names": [{"displayName": name}],
        "emailAddresses": [{"value": email}],
        "phoneNumbers": [{"value": phone}],
    }


def test_list_contacts_parses_people() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/people/me/connections")
        assert request.headers["authorization"] == "Bearer access-token"
        return httpx.Response(200, json={"connections": [_person("Ali", "ali@x.com", "+60123")]})

    contacts = asyncio.run(_api(handler).list_contacts())
    assert contacts[0]["name"] == "Ali"
    assert contacts[0]["emails"] == ["ali@x.com"]
    assert contacts[0]["phones"] == ["+60123"]


def test_search_contacts_parses_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/people:searchContacts")
        assert request.url.params.get("query") == "aisyah"
        return httpx.Response(200, json={"results": [{"person": _person("Aisyah", "a@x.com", "")}]})

    contacts = asyncio.run(_api(handler).search_contacts("aisyah"))
    assert contacts[0]["name"] == "Aisyah"
    assert contacts[0]["phones"] == []  # empty phone dropped


def test_contacts_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with pytest.raises(ContactsApiError):
        asyncio.run(_api(handler).list_contacts())


def test_connector_inert_without_token() -> None:
    tools = {t.name: t for t in GoogleContactsConnector().tools(ConnectorContext(user_id="u"))}
    result = asyncio.run(tools["search_contacts"].handler(query="ali"))
    assert result["connected"] is False


def test_connector_searches_with_token(monkeypatch) -> None:
    class FakeContactsApi:
        def __init__(self, token: str) -> None:
            assert token == "c-token"

        async def search_contacts(self, query: str, *, max_results: int = 10) -> list[dict]:
            return [{"name": "Ali", "emails": ["ali@x.com"], "phones": ["+60123"]}]

    monkeypatch.setattr("app.connectors.google_contacts.ContactsApi", FakeContactsApi)
    ctx = ConnectorContext(user_id="u", credentials={"contacts_access_token": "c-token"})
    tools = {t.name: t for t in GoogleContactsConnector().tools(ctx)}
    result = asyncio.run(tools["search_contacts"].handler(query="ali"))
    assert result["connected"] is True
    assert result["contacts"][0]["name"] == "Ali"


def test_scope_connector_keys_match_registered_connectors() -> None:
    """Guard: every scope→connector key must be a real registered connector key.

    (Catches the class of bug where the credentials map used a key the connector's
    manifest doesn't have, so the token never reached the connector.)
    """
    import app.main  # noqa: F401 — ensures connectors are discovered
    from app.connectors.registry import registry
    from app.integrations.credentials import _SCOPE_TO_CONNECTOR

    registered = set(registry.keys())
    for _scope, (connector_key, _cred_key) in _SCOPE_TO_CONNECTOR.items():
        assert connector_key in registered, f"{connector_key} is not a registered connector"
