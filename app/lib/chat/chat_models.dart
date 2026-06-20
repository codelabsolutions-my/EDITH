import '../ws/events.dart';

/// Who authored a chat message.
enum MessageRole { user, edith }

/// A single message bubble in the conversation.
class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.text,
    this.isStreaming = false,
  });

  final MessageRole role;
  final String text;

  /// True while EDITH is still streaming chunks into this message.
  final bool isStreaming;

  ChatMessage copyWith({String? text, bool? isStreaming}) {
    return ChatMessage(
      role: role,
      text: text ?? this.text,
      isStreaming: isStreaming ?? this.isStreaming,
    );
  }
}

/// A pending action awaiting the user's yes/no.
class PendingConfirm {
  const PendingConfirm({required this.actionId, required this.summary});

  final String actionId;
  final String summary;
}

/// Immutable snapshot of the conversation surface.
class ChatState {
  const ChatState({
    this.messages = const [],
    this.sessionState = SessionState.idle,
    this.pendingConfirm,
    this.activeTool,
    this.errorMessage,
    this.connected = false,
  });

  final List<ChatMessage> messages;
  final SessionState sessionState;
  final PendingConfirm? pendingConfirm;

  /// Name of a tool currently running, if any.
  final String? activeTool;
  final String? errorMessage;
  final bool connected;

  /// Input is allowed only when connected, idle, and not awaiting a confirm.
  bool get canSend =>
      connected &&
      pendingConfirm == null &&
      sessionState != SessionState.thinking &&
      sessionState != SessionState.speaking;

  bool get isBusy =>
      sessionState == SessionState.thinking ||
      sessionState == SessionState.speaking;

  ChatState copyWith({
    List<ChatMessage>? messages,
    SessionState? sessionState,
    PendingConfirm? pendingConfirm,
    bool clearPendingConfirm = false,
    String? activeTool,
    bool clearActiveTool = false,
    String? errorMessage,
    bool clearError = false,
    bool? connected,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      sessionState: sessionState ?? this.sessionState,
      pendingConfirm:
          clearPendingConfirm ? null : (pendingConfirm ?? this.pendingConfirm),
      activeTool: clearActiveTool ? null : (activeTool ?? this.activeTool),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      connected: connected ?? this.connected,
    );
  }
}
