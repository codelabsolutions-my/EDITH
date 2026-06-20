# Phase 1 — Runtime architecture (Transport + agent loop)

> Load-bearing design for the EDITH agent runtime. Status: **M0 implemented**
> (text-mode, `StubLLM`, in-memory memory, stub auth). Voice (`voice/pipeline.py`,
> `asr.py`, `tts.py`, `vad.py`) and real auth/DB land in M1/M2 against the same
> seams — nothing in this doc changes when they do.

## Core principle — text and voice are one loop

The agent loop never knows whether it drives a microphone or a chat box.
`Transport` is the *only* thing that differs between modes. Data flows as **typed
events**, not raw bytes: the text stub emits a `TextIn`; the future voice pipeline
emits a `Transcript`/`TextIn` from ILMU ASR. The orchestrator (`AgentLoop`) cannot
tell the difference, so confirmation, barge-in, tool dispatch and memory are
written exactly once.

```
WS client ⇄ ws.py ⇄ Session ⇄ Transport ⇄ AgentLoop ⇄ LLMProvider
                       │            │           │            └ StubLLM (M0) / ILMU / frontier
                       │            │           ├ ToolCatalog → connectors.registry
                       │            │           ├ ConfirmGate (server-enforced)
                       │            │           └ Memory (in-memory M0 → Postgres M1)
                       │            └ TextTransport (M0) / VoicePipeline (M2)
                       └ demux WS frames → InboundEvent queue
```

## Event vocabulary (`events.py`)

All events are **frozen dataclasses**. Inbound events flow client → loop; outbound
events flow loop → client.

**Inbound:** `AudioFrameIn(data: bytes)` (ignored in M0), `TextIn(text: str)`,
`ConfirmReply(action_id: str, ok: bool)`, `BargeInHint()`.

**Outbound:** `StatusEvent(state: Status)` where `Status ∈
{LISTENING, THINKING, SPEAKING, IDLE}`; `Transcript(role, text, final)`;
`LLMToken(text)` (one streamed chunk of EDITH's reply); `AudioFrameOut(data)`
(voice only); `ConfirmRequest(action_id, summary)`; `ToolEvent(name, state)` with
`state ∈ {running, done, error}`; `ErrorEvent(code, message)`; `TurnComplete()`.

## Transport seam (`voice/transport.py`)

`Transport` is an ABC — the single seam between the loop and the wire.

```python
class Transport(ABC):
    def user_turns(self) -> AsyncIterator[UserTurn]: ...
    async def emit(self, event: OutboundEvent) -> None: ...
    async def set_status(self, status: Status) -> None: ...
    async def request_confirm(self, action_id: str, summary: str) -> bool: ...
    def barge_in_signal(self) -> asyncio.Event: ...
    async def flush_output(self) -> None: ...
    async def close(self) -> None: ...

@dataclass(frozen=True)
class UserTurn:
    text: str
    audio_present: bool
```

`request_confirm` emits a `ConfirmRequest` and **blocks** until the matching
`ConfirmReply` arrives (a future keyed by `action_id`). `barge_in_signal()` returns
an `asyncio.Event` that is set when the user interrupts mid-turn.

### `TextTransport` (M0, `voice/text_transport.py`)

- Consumes an `asyncio.Queue[InboundEvent]` fed by the WS demux.
- `user_turns()` yields one `UserTurn(text, audio_present=False)` per `TextIn`;
  on `ConfirmReply` it resolves the pending confirm future instead of yielding.
- `emit()` serializes outbound events to JSON via an injected `ws_send` callable.
  Key mapping: `LLMToken → {"type":"transcript","role":"edith","text":…,
  "final":false}`; `TurnComplete → {"type":"turn_end"}`; `StatusEvent →
  {"type":"status","state":…}`; `ToolEvent → {"type":"tool_event","name":…,
  "state":…}`; `ConfirmRequest → {"type":"confirm_request",…}`;
  `ErrorEvent → {"type":"error",…}`.
- A `TextIn` arriving while a turn is active sets the barge-in event.

## LLM provider seam (`agent/llm.py`)

```python
class LLMProvider(ABC):
    def stream(self, messages, tools, *, cancel) -> AsyncIterator[LLMDelta]: ...

LLMDelta = TextDelta(text) | ToolCallDelta(call: ToolCall) | TurnEnd(finish_reason)
ToolSpec(name, description, parameters)        # JSON-schema parameters
ToolCall(id, name, arguments)
```

**`StubLLM` (M0):** deterministic, no network. It scans the latest user message for
trigger phrases and emits the matching `ToolCallDelta`:

| Trigger substring | Tool call |
|---|---|
| `remember` | `remember(text=<text after 'remember'>)` |
| `what time` / `current time` | `current_time()` |
| `self destruct` | `self_destruct()` (CONFIRM) |
| `echo ` | `echo(text=<text after 'echo '>)` |

When the latest message is a **tool result** (the loop fed one back), `StubLLM`
emits a short acknowledging `TextDelta` then `TurnEnd("stop")`. Otherwise, with no
trigger, it emits a canned greeting/ack and `TurnEnd("stop")`.

## Tool catalog (`agent/catalog.py`)

`ToolCatalog(registry, user_id, cred_lookup)` adapts the **existing**
`connectors.registry` (no second registry):

- `specs() -> list[ToolSpec]` iterates `registry.all()`, builds a
  `ConnectorContext(user_id, credentials=cred_lookup(key))` per connector, and
  flattens every `Tool` into a `ToolSpec`.
- `lookup(name) -> Tool | None` returns the live `Tool` (handler bound).
- **Namespacing:** tool names are kept bare when globally unique (foundational +
  `example_echo` are unique). On a collision across connectors, the *later*
  connector's tool is exposed as `"{connector_key}.{tool_name}"`; the first
  keeps the bare name. M0 never collides but the guard is in place.

## Confirmation gate (`agent/confirm.py`)

`ConfirmGate.await_reply(action_id, summary, transport, cancel) -> bool` races
`transport.request_confirm(...)` against the `cancel` event. If `cancel` fires
first it raises `TurnCancelled`. This is **server-enforced and model-independent**:
an unreliable LLM cannot make a `CONFIRM` tool run without an explicit `ok:true`.

## Agent loop (`agent/loop.py`)

`AgentLoop.run()` drives the whole turn lifecycle:

```
async for turn in transport.user_turns():
    cancel = Event()  ; watcher links transport.barge_in_signal() → cancel
    set_status(THINKING)
    memory = recall(user_id, turn.text)          # injected into the system prompt
    messages = build(system_prompt(memory), history, turn.text)
    loop:
        async for delta in llm.stream(messages, specs, cancel=cancel):
            if cancel.is_set(): raise TurnCancelled
            TextDelta   → emit LLMToken, accumulate reply text
            ToolCallDelta → collect call
            TurnEnd     → break
        if tool calls:
            for call in calls: result = _dispatch(call)   # appends tool result msg
            continue                                       # re-stream with results
        else:
            break
    flush_output() ; emit TurnComplete ; set_status(IDLE)
    schedule detached memory.extract_after_turn(...)       # off the latency path
# TurnCancelled is caught here → set_status(LISTENING) → continue to next turn
```

`_dispatch(call)`:
1. `tool = catalog.lookup(call.name)`; unknown → `ToolEvent(error)` + error result.
2. emit `ToolEvent(name, running)`.
3. if `tool.tool_class is ToolClass.CONFIRM` → `ConfirmGate.await_reply(...)`;
   on `ok:false` skip (no run) and return a "declined" result.
4. `result = await tool.handler(**call.arguments)`; append to in-memory action log;
   emit `ToolEvent(name, done)`.
5. on exception → emit `ToolEvent(name, error)`, return `{"error": str(exc)}`.

### Barge-in

One `asyncio.Event` (`cancel`) per turn. A watcher task waits on
`transport.barge_in_signal()` and sets `cancel`. The loop checks `cancel.is_set()`
between deltas (and `stream()` receives `cancel` so a real provider can abort its
HTTP stream). On cancel the loop raises `TurnCancelled`, which `run()` catches →
`set_status(LISTENING)` → proceeds to the next user turn. AUTO (reversible) tools
already in flight may finish; their results are discarded. CONFIRM tools never fire
without an explicit reply, so nothing irreversible escapes a barge-in.

## Memory (`agent/tools/foundational.py` + in-memory store, M0)

- `recall(user_id, query)` is called at turn start; the result is injected into the
  system prompt under "What you remember about the user:".
- `remember(text)` / `recall(query)` are also AUTO foundational tools for explicit
  use. `current_time` returns ISO-8601 now; `web_lookup` returns a **canned** dict
  (no network in M0).
- **M0 store:** a module-level `dict[user_id → list[str]]`. **TODO(M1):** swap for
  the Postgres `memories` table with tsvector recall (see `phase-1-data.md`).
- `extract_after_turn` is a trivial heuristic in M0 (no-op / cheap), scheduled
  detached after `TurnComplete` so it never adds turn latency. **TODO(M1):**
  LLM/heuristic durable-fact extraction with dedupe.

## Session + WebSocket (`session.py`, `ws.py`, `main.py`)

- `Session(user_id, ws_send, ...)` builds a `TextTransport`, a `ToolCatalog`, an
  in-memory `Memory`, a `ConfirmGate`, a `StubLLM`, and an `AgentLoop`. `run()`
  uses an `asyncio.TaskGroup`: one task demuxes the WS into the inbound queue
  (`bytes → AudioFrameIn` (ignored in M0); JSON `text → TextIn`,
  `confirm → ConfirmReply`, `barge_in → BargeInHint`); a `TextIn` arriving while a
  turn is active sets barge-in. The other task runs `AgentLoop.run()`.
- `ws.py`: `@app.websocket("/ws")` accepts, requires a first
  `{"type":"auth","token":…}` frame, calls `verify_jwt(token)`, replies
  `{"type":"auth_ok","user":{…}}`, then runs the Session; cleans up on disconnect.
  **M0 stub:** `verify_jwt` accepts any non-empty token and returns a deterministic
  fake user id. **TODO(M1):** real OIDC/JWT verification (see `phase-1-auth.md`).
- `main.py`: app factory; on startup `registry.discover(...)` over
  `connectors.examples` and the foundational package so all connectors register.

## Protocol (M0-relevant adjustments to `phase-1-mvp.md`)

1. `text` is a **first-class** turn trigger: `{"type":"text","content":"…"}`.
2. New outbound `{"type":"turn_end"}` (from `TurnComplete`) re-enables text input.
3. `status` applies in text mode (`thinking`/`idle` drive a spinner).
4. `tool_event` gains an `error` state.
5. `confirm_request.action_id` is echoed back exactly in the `confirm` reply.

## Stubbed for later milestones

| Stub (M0) | Real (milestone) |
|---|---|
| `verify_jwt` accepts any token | OIDC RP + JWT verify/refresh (M1) |
| module-level dict memory | Postgres `memories` + tsvector (M1) |
| `extract_after_turn` heuristic | LLM extraction + dedupe (M1) |
| in-memory action log | `action_log` table (M1) |
| `web_lookup` canned dict | real search API (post-MVP) |
| `StubLLM` | ILMU LLM / frontier fallback (M2/bake-off) |
| `TextTransport` only | `VoicePipeline` (VAD→ASR→loop→TTS) (M2) |
