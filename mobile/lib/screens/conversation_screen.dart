import 'package:flutter/material.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import '../services/api_client.dart';

class ChatEntry {
  ChatEntry({required this.role, required this.text});
  final String role; // user | assistant
  final String text;
}

/// Phase 2: proves the mic -> STT -> API -> UI loop (medai_spec.yaml voice_pipeline /
/// architecture.canonical_pipeline, up through TEXT_RESPONSE). No medical reasoning happens
/// here yet — see app/conversation/stub_reply.py on the backend.
///
/// Voice is the primary input (ux.voice_first), but per ux.accessibility's
/// text_always_available requirement, typed text is always an equally valid way to send a
/// message — this also makes the flow testable without a live microphone.
class ConversationScreen extends StatefulWidget {
  const ConversationScreen({super.key, this.apiClient});

  /// Injectable for widget tests; defaults to a real ApiClient otherwise.
  final ApiClient? apiClient;

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends State<ConversationScreen> {
  late final ApiClient _apiClient = widget.apiClient ?? ApiClient();
  final _speech = stt.SpeechToText();
  final _textController = TextEditingController();
  final _messages = <ChatEntry>[];
  final _scrollController = ScrollController();

  String? _conversationId;
  bool _listening = false;
  bool _sending = false;
  bool _speechAvailable = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      _conversationId = await _apiClient.createConversation();
    } catch (e) {
      setState(() => _error = 'Could not reach MEDAI backend: $e');
      return;
    }

    try {
      // No platform implementation is registered in a headless/widget-test environment —
      // degrade to "speech unavailable" rather than crashing the whole screen.
      _speechAvailable = await _speech.initialize(
        onError: (error) => setState(() => _error = error.errorMsg),
      );
    } catch (_) {
      _speechAvailable = false;
    }
    if (mounted) setState(() {});
  }

  Future<void> _toggleListening() async {
    if (!_speechAvailable) {
      setState(() => _error = 'Speech recognition is not available on this device/browser.');
      return;
    }

    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      return;
    }

    setState(() {
      _listening = true;
      _error = null;
    });
    await _speech.listen(
      onResult: (result) {
        _textController.text = result.recognizedWords;
        if (result.finalResult) {
          setState(() => _listening = false);
        }
      },
    );
  }

  Future<void> _send() async {
    final text = _textController.text.trim();
    if (text.isEmpty || _conversationId == null || _sending) return;

    setState(() {
      _sending = true;
      _error = null;
      _messages.add(ChatEntry(role: 'user', text: text));
    });
    _textController.clear();
    _scrollToBottom();

    try {
      final reply = await _apiClient.sendMessage(conversationId: _conversationId!, content: text);
      setState(() => _messages.add(ChatEntry(role: 'assistant', text: reply)));
    } catch (e) {
      setState(() => _error = 'Could not send message: $e');
    } finally {
      setState(() => _sending = false);
      _scrollToBottom();
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    if (_speechAvailable) {
      _speech.stop();
    }
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Talk to Health AI')),
      body: Column(
        children: [
          if (_error != null)
            Container(
              width: double.infinity,
              color: Theme.of(context).colorScheme.errorContainer,
              padding: const EdgeInsets.all(12),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer)),
            ),
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final entry = _messages[index];
                final isUser = entry.role == 'user';
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    key: ValueKey('message_$index'),
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    padding: const EdgeInsets.all(12),
                    constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                    decoration: BoxDecoration(
                      color: isUser
                          ? Theme.of(context).colorScheme.primaryContainer
                          : Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(entry.text),
                  ),
                );
              },
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(8.0),
              child: Row(
                children: [
                  IconButton(
                    tooltip: _listening ? 'Stop listening' : 'Speak',
                    iconSize: 32,
                    icon: Icon(_listening ? Icons.mic : Icons.mic_none),
                    color: _listening ? Theme.of(context).colorScheme.error : null,
                    onPressed: _toggleListening,
                  ),
                  Expanded(
                    child: TextField(
                      controller: _textController,
                      decoration: const InputDecoration(hintText: 'Speak, or type your message'),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Send',
                    icon: _sending
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.send),
                    onPressed: _sending ? null : _send,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
