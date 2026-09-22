import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:medai/services/speech_playback_service.dart';

class FakeAudioBackend implements AudioBackend {
  final calls = <String>[];
  final _completeController = StreamController<void>.broadcast();
  bool _isPlaying = false;

  bool shouldThrowOnPlay = false;
  bool shouldThrowOnStop = false;

  @override
  bool get isPlaying => _isPlaying;

  @override
  Future<void> play(Uint8List bytes) async {
    calls.add('play');
    if (shouldThrowOnPlay) {
      throw Exception('simulated platform playback failure');
    }
    _isPlaying = true;
  }

  @override
  Future<void> stop() async {
    calls.add('stop');
    _isPlaying = false;
    if (shouldThrowOnStop) {
      throw Exception('simulated platform stop failure');
    }
  }

  @override
  Stream<void> get onComplete => _completeController.stream;

  void simulateCompletion() => _completeController.add(null);
}

void main() {
  group('SpeechPlaybackService', () {
    test('play() always stops any current playback first (barge-in)', () async {
      final backend = FakeAudioBackend();
      final service = SpeechPlaybackService(backend: backend);

      await service.play(Uint8List.fromList([1, 2, 3]));

      expect(backend.calls, ['stop', 'play']);
    });

    test('a second play() call interrupts the first, not overlaps it', () async {
      final backend = FakeAudioBackend();
      final service = SpeechPlaybackService(backend: backend);

      await service.play(Uint8List.fromList([1]));
      await service.play(Uint8List.fromList([2]));

      expect(backend.calls, ['stop', 'play', 'stop', 'play']);
    });

    test('a playback failure raises TtsPlaybackException, not a silent failure', () async {
      final backend = FakeAudioBackend()..shouldThrowOnPlay = true;
      final service = SpeechPlaybackService(backend: backend);

      expect(
        () => service.play(Uint8List.fromList([1, 2, 3])),
        throwsA(isA<TtsPlaybackException>()),
      );
    });

    test('stop() never throws even if the backend fails to stop', () async {
      final backend = FakeAudioBackend()..shouldThrowOnStop = true;
      final service = SpeechPlaybackService(backend: backend);

      await expectLater(service.stop(), completes);
    });

    test('stop() is safe to call when nothing is playing', () async {
      final backend = FakeAudioBackend();
      final service = SpeechPlaybackService(backend: backend);

      await expectLater(service.stop(), completes);
      expect(backend.calls, ['stop']);
    });

    test('onComplete forwards the backend completion event', () async {
      final backend = FakeAudioBackend();
      final service = SpeechPlaybackService(backend: backend);

      final future = service.onComplete.first;
      backend.simulateCompletion();

      await expectLater(future, completes);
    });
  });
}
