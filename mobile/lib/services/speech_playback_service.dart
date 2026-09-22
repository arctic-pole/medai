import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';

/// Raised on any playback failure — never fails silently, so a caller can fall back to the
/// text response it already has (ux.accessibility.text_always_available; TTS is optional, not
/// the only response channel).
class TtsPlaybackException implements Exception {
  TtsPlaybackException(this.message);
  final String message;

  @override
  String toString() => 'TtsPlaybackException: $message';
}

/// Thin seam over the real audio backend, so SpeechPlaybackService's interrupt/barge-in and
/// error-handling logic is unit-testable without a platform audio channel (the audioplayers
/// package needs a real platform implementation, unavailable in a widget-test environment).
abstract class AudioBackend {
  Future<void> play(Uint8List bytes);
  Future<void> stop();
  bool get isPlaying;

  /// Fires when playback finishes on its own (not via an explicit stop()) — lets the UI clear
  /// a "playing" indicator without polling.
  Stream<void> get onComplete;
}

class AudioplayersBackend implements AudioBackend {
  final AudioPlayer _player = AudioPlayer();

  @override
  bool get isPlaying => _player.state == PlayerState.playing;

  @override
  Future<void> play(Uint8List bytes) => _player.play(BytesSource(bytes));

  @override
  Future<void> stop() => _player.stop();

  @override
  Stream<void> get onComplete => _player.onPlayerComplete;
}

/// voice_pipeline's SPEAKER step. Plays audio bytes returned by the backend's
/// POST /assessment/speech (backend/app/api/assessment.py) — synthesis itself happens
/// server-side (backend/app/providers/tts/), so this service is a vendor-agnostic playback
/// wrapper, not a TTS engine itself.
class SpeechPlaybackService {
  SpeechPlaybackService({AudioBackend? backend}) : _backend = backend ?? AudioplayersBackend();

  final AudioBackend _backend;

  bool get isPlaying => _backend.isPlaying;

  Stream<void> get onComplete => _backend.onComplete;

  /// Plays [audioBytes]. voice_pipeline.rules: "User must be able to interrupt TTS and
  /// continue speaking" — barge-in is handled by always stopping any current playback first,
  /// so calling play() again (e.g. the user taps Play on a new response, or starts speaking)
  /// always interrupts whatever was playing rather than overlapping it. A playback failure
  /// raises TtsPlaybackException rather than failing silently, so the caller can show an error
  /// and fall back to the text it already has.
  Future<void> play(Uint8List audioBytes) async {
    await stop();
    try {
      await _backend.play(audioBytes);
    } catch (e) {
      throw TtsPlaybackException('failed to play audio: $e');
    }
  }

  /// Explicit interrupt/barge-in entry point, and also safe to call when nothing is playing.
  Future<void> stop() async {
    try {
      await _backend.stop();
    } catch (_) {
      // Stopping a player that isn't playing (or a platform hiccup) must never surface as a
      // user-facing error — stop() is a best-effort "make sure nothing is playing" call.
    }
  }
}
