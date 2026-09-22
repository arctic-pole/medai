import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medai/screens/conversation_screen.dart';
import 'package:medai/services/api_client.dart';
import 'package:medai/services/speech_playback_service.dart';

/// Bypasses real network/secure-storage calls so this test doesn't need a running backend,
/// a real device keystore, or a microphone — exercises the ux.accessibility text_always_available
/// path (typed text), not the voice/STT path, which needs a real device/browser to verify.
class FakeApiClient extends ApiClient {
  final sentMessages = <String>[];
  String assessmentSummary = 'Possible explanations include a tension headache.';
  Object? assessmentSpeechError;

  @override
  Future<String> createConversation() async => 'fake-conversation-id';

  @override
  Future<String> sendMessage({required String conversationId, required String content}) async {
    sentMessages.add(content);
    return 'stub reply to: $content';
  }

  @override
  Future<Map<String, dynamic>> getAssessment({required String conversationId}) async {
    return {'summary': assessmentSummary};
  }

  @override
  Future<Uint8List> fetchAssessmentSpeech({required String conversationId}) async {
    if (assessmentSpeechError != null) throw assessmentSpeechError!;
    return Uint8List.fromList([1, 2, 3]);
  }
}

class FakeAudioBackend implements AudioBackend {
  final calls = <String>[];
  final _completeController = StreamController<void>.broadcast();
  bool shouldThrowOnPlay = false;

  @override
  bool get isPlaying => calls.isNotEmpty && calls.last == 'play';

  @override
  Future<void> play(Uint8List bytes) async {
    calls.add('play');
    if (shouldThrowOnPlay) throw Exception('simulated playback failure');
  }

  @override
  Future<void> stop() async => calls.add('stop');

  @override
  Stream<void> get onComplete => _completeController.stream;
}

void main() {
  testWidgets('typing and sending a message shows both bubbles', (WidgetTester tester) async {
    final fakeApi = FakeApiClient();

    await tester.pumpWidget(MaterialApp(home: ConversationScreen(apiClient: fakeApi)));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'I have a headache');
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(fakeApi.sentMessages, ['I have a headache']);
    expect(find.text('I have a headache'), findsOneWidget);
    expect(find.text('stub reply to: I have a headache'), findsOneWidget);
  });

  testWidgets('Get assessment shows the validated summary as text, with a Play control',
      (WidgetTester tester) async {
    final fakeApi = FakeApiClient();
    final backend = FakeAudioBackend();

    await tester.pumpWidget(MaterialApp(
      home: ConversationScreen(apiClient: fakeApi, speechPlaybackService: SpeechPlaybackService(backend: backend)),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Get assessment'));
    await tester.pumpAndSettle();

    // Text is shown immediately — before Play is ever tapped, i.e. before any audio call.
    expect(find.text(fakeApi.assessmentSummary), findsOneWidget);
    expect(backend.calls, isEmpty);
    expect(find.byTooltip('Play'), findsOneWidget);
  });

  testWidgets('tapping Play fetches and plays audio, tapping again (or Stop) interrupts it',
      (WidgetTester tester) async {
    final fakeApi = FakeApiClient();
    final backend = FakeAudioBackend();

    await tester.pumpWidget(MaterialApp(
      home: ConversationScreen(apiClient: fakeApi, speechPlaybackService: SpeechPlaybackService(backend: backend)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Get assessment'));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Play'));
    await tester.pumpAndSettle();

    expect(backend.calls, ['stop', 'play']); // SpeechPlaybackService.play() always stops first
    expect(find.byTooltip('Stop'), findsOneWidget);

    await tester.tap(find.byTooltip('Stop'));
    await tester.pumpAndSettle();

    expect(backend.calls, ['stop', 'play', 'stop']);
    expect(find.byTooltip('Play'), findsOneWidget);
  });

  testWidgets('a TTS fetch failure is shown inline without removing the already-shown text',
      (WidgetTester tester) async {
    final fakeApi = FakeApiClient()..assessmentSpeechError = Exception('TTS_ERROR: engine unavailable');
    final backend = FakeAudioBackend();

    await tester.pumpWidget(MaterialApp(
      home: ConversationScreen(apiClient: fakeApi, speechPlaybackService: SpeechPlaybackService(backend: backend)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Get assessment'));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Play'));
    await tester.pumpAndSettle();

    // The validated text response is untouched by the playback failure.
    expect(find.text(fakeApi.assessmentSummary), findsOneWidget);
    expect(find.textContaining('Could not play audio'), findsOneWidget);
    expect(backend.calls, isEmpty); // fetch failed before any backend playback call
  });

  testWidgets('activating the microphone interrupts any assessment audio currently playing (barge-in)',
      (WidgetTester tester) async {
    final fakeApi = FakeApiClient();
    final backend = FakeAudioBackend();

    await tester.pumpWidget(MaterialApp(
      home: ConversationScreen(apiClient: fakeApi, speechPlaybackService: SpeechPlaybackService(backend: backend)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Get assessment'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Play'));
    await tester.pumpAndSettle();
    expect(backend.calls, ['stop', 'play']);

    // Speech recognition isn't available in this widget-test environment (no platform
    // implementation registered), but _toggleListening() stops playback unconditionally,
    // before checking availability — exactly so barge-in works even on the very first tap.
    await tester.tap(find.byTooltip('Speak'));
    await tester.pumpAndSettle();

    expect(backend.calls, ['stop', 'play', 'stop']);
  });
}
