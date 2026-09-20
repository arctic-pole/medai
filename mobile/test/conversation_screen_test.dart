import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medai/screens/conversation_screen.dart';
import 'package:medai/services/api_client.dart';

/// Bypasses real network/secure-storage calls so this test doesn't need a running backend,
/// a real device keystore, or a microphone — exercises the ux.accessibility text_always_available
/// path (typed text), not the voice/STT path, which needs a real device/browser to verify.
class FakeApiClient extends ApiClient {
  final sentMessages = <String>[];

  @override
  Future<String> createConversation() async => 'fake-conversation-id';

  @override
  Future<String> sendMessage({required String conversationId, required String content}) async {
    sentMessages.add(content);
    return 'stub reply to: $content';
  }
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
}
