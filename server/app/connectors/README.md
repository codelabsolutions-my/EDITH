# Writing an EDITH connector

A **connector** teaches EDITH how to use a third-party service. It exposes a set
of **tools** (actions) that the agent can call during a conversation. This is the
primary way to extend EDITH — and the contribution we've optimized the repo for.

> Before you start, skim the [connector security model](../../../SECURITY.md#connector-security-model).
> We only accept **official, ToS-compliant** APIs. No scraping, no unofficial
> clients, nothing that could get a user's account banned.

## The contract

Implement [`Connector`](base.py) by setting a `manifest` and implementing
`tools()`:

```python
from app.connectors import (
    AuthKind, Connector, ConnectorContext, ConnectorManifest,
    OAuthConfig, Tool, ToolClass, register,
)

@register
class TodoistConnector(Connector):
    manifest = ConnectorManifest(
        key="todoist",                 # unique, snake_case
        name="Todoist",
        description="Read and manage Todoist tasks.",
        auth=AuthKind.OAUTH2,
        oauth=OAuthConfig(
            authorize_url="https://todoist.com/oauth/authorize",
            token_url="https://todoist.com/oauth/access_token",
            scopes=("data:read",),     # minimal baseline; ask for more just-in-time
        ),
        maintainer="your-github-handle",
        tags=("tasks",),
    )

    def tools(self, ctx: ConnectorContext) -> list[Tool]:
        return [
            Tool(
                name="list_tasks",
                description="List the user's active tasks.",
                parameters={"type": "object", "properties": {}},
                tool_class=ToolClass.AUTO,        # read -> auto
                handler=self._list_tasks,
            ),
            Tool(
                name="delete_task",
                description="Delete a task by id.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                tool_class=ToolClass.CONFIRM,     # irreversible -> confirm
                handler=self._delete_task,
            ),
        ]

    async def _list_tasks(self) -> list[dict]:
        token = ...  # ctx.credentials provides the refreshed access token
        ...

    async def _delete_task(self, task_id: str) -> dict:
        ...
```

### The rules (also enforced by the conformance test)

| Rule | Why |
|------|-----|
| `key` is unique, snake_case (`^[a-z][a-z0-9_]*$`) | Stable identifier |
| `auth=OAUTH2` ⇒ provide an `oauth` config | Can't connect otherwise |
| Each tool's `parameters` is a JSON-Schema **object** | The agent calls tools by schema |
| Tool names are unique within the connector | Unambiguous dispatch |
| Every handler is an **async** function | Non-blocking server |
| External/irreversible tools are **`CONFIRM`** | The trust model — see below |

### `AUTO` vs `CONFIRM`

This classification is the heart of EDITH's trust model. Get it right:

- **`AUTO`** — reversible, local, or read-only: list/read, draft, add a to-do, set
  a reminder, summarize.
- **`CONFIRM`** — external or hard to undo: send a message/email, delete, modify
  something involving other people, post publicly, pay, unlock. EDITH will state
  the action and wait for a "yes" before your handler runs.

When in doubt, choose `CONFIRM`.

## Auth & credentials

- For `OAUTH2`, declare the **minimum** baseline scopes. Request feature-specific
  scopes **incrementally** (just-in-time) — never everything at signup.
- Your handlers receive already-refreshed credentials via `ctx.credentials`.
  Never log tokens; never send user data anywhere except the service's own API.
- Implement clean revocation: stop touching data the moment a user disconnects.

## Testing your connector

```bash
make test-connectors      # runs the conformance suite against all connectors
```

The suite validates every registered connector against the contract above. Add
behavioural tests for your handlers in `server/tests/` too.

## Submitting

1. One connector per PR; branch `connector/<service>`.
2. Open the PR with the **New connector** template; sign off your commits
   (`git commit -s`).
3. A maintainer reviews against the
   [security checklist](../../../SECURITY.md#review-checklist-maintainers).
4. Community connectors are labeled as such; users opt in explicitly.

Questions? Open a Discussion. Happy building! 🔌
