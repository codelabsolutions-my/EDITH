import '../ws/events.dart';
import 'chat_models.dart';

/// Pure reduction of an [InboundEvent] onto the current [ChatState].
///
/// Kept free of Riverpod/socket dependencies so the accumulation rules are
/// directly unit-testable:
///   * EDITH transcript chunks append into a single streaming message.
///   * `user` transcripts are echoed as their own (already-final) message.
///   * `turn_end` finalizes the streaming EDITH message.
///   * `confirm_request` surfaces a pending confirm.
ChatState reduce(ChatState state, InboundEvent event) {
  switch (event) {
    case AuthOkEvent():
      return state.copyWith(connected: true, clearError: true);

    case StatusEvent(:final sessionState):
      return state.copyWith(sessionState: sessionState);

    case TranscriptEvent(:final isUser, :final text):
      return isUser
          ? _appendUserMessage(state, text)
          : _accumulateEdith(state, text);

    case ToolEvent(:final name, :final toolState):
      return toolState == ToolState.running
          ? state.copyWith(activeTool: name)
          : state.copyWith(clearActiveTool: true);

    case ConfirmRequestEvent(:final actionId, :final summary):
      return state.copyWith(
        pendingConfirm:
            PendingConfirm(actionId: actionId, summary: summary),
      );

    case TurnEndEvent():
      return _finalizeStreaming(state);

    case ErrorEvent(:final message):
      return state.copyWith(errorMessage: message);

    case UnknownEvent():
      return state;
  }
}

ChatState _appendUserMessage(ChatState state, String text) {
  return state.copyWith(
    messages: [
      ...state.messages,
      ChatMessage(role: MessageRole.user, text: text),
    ],
  );
}

ChatState _accumulateEdith(ChatState state, String chunk) {
  final messages = [...state.messages];
  final last = messages.isNotEmpty ? messages.last : null;
  if (last != null && last.role == MessageRole.edith && last.isStreaming) {
    messages[messages.length - 1] =
        last.copyWith(text: last.text + chunk);
  } else {
    messages.add(
      ChatMessage(role: MessageRole.edith, text: chunk, isStreaming: true),
    );
  }
  return state.copyWith(messages: messages);
}

ChatState _finalizeStreaming(ChatState state) {
  final messages = [...state.messages];
  if (messages.isNotEmpty && messages.last.isStreaming) {
    messages[messages.length - 1] =
        messages.last.copyWith(isStreaming: false);
  }
  return state.copyWith(
    messages: messages,
    sessionState: SessionState.idle,
    clearActiveTool: true,
  );
}
