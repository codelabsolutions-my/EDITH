# 0002. Voice pipeline & agent LLM — outcome of the ILMU spike

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Core team
- **Supersedes:** the "streaming voice pipeline" + "ILMU-LLM-default / frontier-fallback" assumptions in `product-design.md` and `phase-1-mvp.md` (pre-spike).

## Context

The voice architecture assumed ILMU offered **streaming** ASR/TTS and a tool-calling-capable LLM. A live spike against `api.ilmu.ai` (YTL AI Labs, OpenAI-compatible) tested these directly.

### Spike findings (measured)

- **STT** `ilmu-asr-v4.2` — file/batch only (`POST /v1/audio/transcriptions`, multipart). **No streaming.** ~2.0s for a 6s clip. **Manglish/code-switching accuracy: excellent** (e.g. "set appointment dengan Dr Lim esok pukul 3 petang" transcribed correctly).
- **TTS** `ilmu-tts-v2` — non-streaming (`POST /v1/audio/speech` → full WAV). ~1.7s for ~6s audio. Output is lowercase, no punctuation.
- **LLM** `ilmu-v3.1` — strong Manglish comprehension/generation, but **unreliable tool-calling**: on `tool_choice:auto` it did not call an available tool; when *forced* it emitted valid JSON but got relative-date math wrong (returned 2025 despite "today is 2026-06-20" in the system prompt).
- **Bonus:** `bge-m3` (embeddings) + `bge-reranker` available → semantic memory is cheap. All endpoints OpenAI-compatible.

## Decision

1. **Voice is turn-based with pseudo-streaming, not true streaming.** Keep ILMU (the Manglish quality is the differentiator). Engineer responsiveness: VAD-tight utterances → batch ASR on endpoint; token-stream the LLM; **synthesize TTS per sentence** and play back-to-back; **barge-in on playback**. Target ~3s to first audio. Reframe the product promise from "fluid real-time voice-to-voice" to **"fast, natural voice turns."**
2. **Agent reasoning/tool-calling uses `nemo-super`** (YTL's Nemotron-based model, built for agentic tool use) — **not** `ilmu-v3.1`. `ilmu-v3.1` may be used for Manglish-heavy generation. This keeps us **single-vendor (YTL/ILMU API)**. A frontier model (Claude/GPT) remains only an **optional escape hatch** behind the LLM abstraction, not a default dependency.
3. **Drop the OpenAI Realtime A/B harness** — there is no streaming to compare against, and single-vendor is preferred.
4. **Memory may use ILMU `bge-m3` embeddings + `bge-reranker`** for semantic recall, in addition to / instead of tsvector lexical search.

## Consequences

- The `StreamingASR`/`StreamingTTS` protocols in the runtime design **absorb this cleanly**: `asr.py` = batch-on-endpoint (one `FinalTranscript`, no partials); `tts.py` = per-sentence chunked. The agent loop, `Transport`, and WS hub are unchanged — the abstraction paid off.
- UX losses vs. true streaming: no live partial transcript while the user speaks; a ~2s ASR floor per turn. Barge-in (interrupting playback) is preserved.
- Integration simplifies to the OpenAI SDK against `https://api.ilmu.ai/v1`.
- **`nemo-super` validated (2026-06-20):** on `tool_choice:auto` it correctly called `set_reminder` with `2026-06-21T10:00` ("esok") and `create_event` with `2026-06-22T14:00` ("next Monday"), valid JSON, in ~0.8s, across Manglish and English. The single-vendor agent is confirmed viable. `nemo-super` is the agent's reasoning/tool model.

## Alternatives considered

- **Streaming via a different provider** — rejected: streaming ASR/TTS vendors don't handle Manglish well, losing the core differentiator.
- **ILMU `v3.1` for tools + prompt engineering** — rejected: proven unreliable on `auto` and on temporal reasoning; `nemo-super` is the purpose-built option.
- **Frontier (Claude/GPT) for reasoning** — kept only as an optional escape hatch, to preserve single-vendor/sovereign positioning.
