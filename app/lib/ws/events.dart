/// Typed model of the JSON frames exchanged over the `/ws` channel.
///
/// Only the inbound (server -> client) frames need rich parsing; outbound
/// frames are built directly in [WsTransport].
library;

/// Connection-status the server reports for the current turn.
enum SessionState { listening, thinking, speaking, idle }

SessionState _stateFromName(String? name) {
  switch (name) {
    case 'listening':
      return SessionState.listening;
    case 'thinking':
      return SessionState.thinking;
    case 'speaking':
      return SessionState.speaking;
    case 'idle':
    default:
      return SessionState.idle;
  }
}

/// Lifecycle of a tool invocation surfaced to the UI.
enum ToolState { running, done, error }

ToolState _toolStateFromName(String? name) {
  switch (name) {
    case 'done':
      return ToolState.done;
    case 'error':
      return ToolState.error;
    case 'running':
    default:
      return ToolState.running;
  }
}

/// Base type for every server -> client frame.
sealed class InboundEvent {
  const InboundEvent();

  /// Decode a decoded-JSON map into the matching event.
  ///
  /// Unknown/malformed frames decode to [UnknownEvent] rather than throwing so
  /// a single bad frame never tears down the stream.
  factory InboundEvent.fromJson(Map<String, dynamic> json) {
    final type = json['type'];
    switch (type) {
      case 'auth_ok':
        return AuthOkEvent(
          user: _asMap(json['user']),
        );
      case 'status':
        return StatusEvent(
          sessionState: _stateFromName(json['state'] as String?),
        );
      case 'transcript':
        return TranscriptEvent(
          role: (json['role'] as String?) ?? 'edith',
          text: (json['text'] as String?) ?? '',
          isFinal: (json['final'] as bool?) ?? false,
        );
      case 'tool_event':
        return ToolEvent(
          name: (json['name'] as String?) ?? '',
          toolState: _toolStateFromName(json['state'] as String?),
        );
      case 'confirm_request':
        return ConfirmRequestEvent(
          actionId: (json['action_id'] as String?) ?? '',
          summary: (json['summary'] as String?) ?? '',
        );
      case 'turn_end':
        return const TurnEndEvent();
      case 'error':
        return ErrorEvent(
          code: (json['code'] as String?) ?? 'unknown',
          message: (json['message'] as String?) ?? '',
        );
      default:
        return UnknownEvent(type: type?.toString() ?? '');
    }
  }
}

Map<String, dynamic> _asMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  return const <String, dynamic>{};
}

/// The auth handshake succeeded.
class AuthOkEvent extends InboundEvent {
  const AuthOkEvent({required this.user});

  final Map<String, dynamic> user;
}

/// The session/turn state changed.
class StatusEvent extends InboundEvent {
  const StatusEvent({required this.sessionState});

  final SessionState sessionState;
}

/// A transcript chunk for either side of the conversation.
///
/// EDITH replies stream as multiple chunks with [isFinal] = false; they are
/// accumulated by the chat layer and finalized on [TurnEndEvent].
class TranscriptEvent extends InboundEvent {
  const TranscriptEvent({
    required this.role,
    required this.text,
    required this.isFinal,
  });

  final String role;
  final String text;
  final bool isFinal;

  bool get isUser => role == 'user';
}

/// A tool started, finished, or failed.
class ToolEvent extends InboundEvent {
  const ToolEvent({required this.name, required this.toolState});

  final String name;
  final ToolState toolState;
}

/// The server is asking the user to confirm a sensitive action.
class ConfirmRequestEvent extends InboundEvent {
  const ConfirmRequestEvent({required this.actionId, required this.summary});

  final String actionId;
  final String summary;
}

/// The turn is over; input may be re-enabled and EDITH's message finalized.
class TurnEndEvent extends InboundEvent {
  const TurnEndEvent();
}

/// A server-reported error.
class ErrorEvent extends InboundEvent {
  const ErrorEvent({required this.code, required this.message});

  final String code;
  final String message;
}

/// A frame whose `type` we do not recognise.
class UnknownEvent extends InboundEvent {
  const UnknownEvent({required this.type});

  final String type;
}
