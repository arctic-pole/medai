# MEDAI Mobile

A Flutter app. Scaffolded via `flutter create --org com.medai --project-name medai .`.

## Status

Phase 2: a "Talk to Health AI" button (`lib/screens/home_screen.dart`) opens
`lib/screens/conversation_screen.dart`, which captures speech via the `speech_to_text` plugin
(on-device/browser-native — see "STT provider decision" below), always shows an equivalent text
input (`ux.accessibility.text_always_available`), and round-trips through the backend's
`/conversations` and `/messages` APIs, showing the Phase 2 scaffold reply. `lib/services/
api_client.dart` also auto-bootstraps a per-device account on first use (temporary — no real
login screen exists yet, see "Known gaps" below).

Verified: `flutter analyze` (clean), `flutter test` (2/2 passing — includes a widget test that
drives the typed-text send path end-to-end against a fake `ApiClient`), `flutter build web`
(succeeds). The voice/STT path and the real backend network call were **not** exercised by an
automated test (no microphone or browser-automation harness in this environment) — verified
manually instead by confirming the backend endpoints work end-to-end via `curl`
(see `docs/API.md`) and that the Flutter code compiles and the equivalent typed-text flow passes.

**STT provider decision:** implemented via Flutter's `speech_to_text` package, which wraps each
platform's native/on-device speech recognition (Android `SpeechRecognizer`, iOS `Speech`
framework, browser Web Speech API on web) rather than a cloud vendor. This avoids needing any
API key or vendor account for the prototype and keeps `SpeechToTextProvider` provider-agnostic
per the spec — the backend has no server-side STT implementation at this phase. Flag if a
cloud STT provider (e.g. for server-side audio processing) is wanted instead.

Proposed layout (see `IMPLEMENTATION_PLAN.md`):

```
lib/
  screens/   # one file per ux.screens entry in medai_spec.yaml
  services/  # API client, audio capture/playback, etc.
  state/     # app state management
```

## Local development

```bash
flutter pub get
flutter analyze
flutter test
flutter run -d chrome     # or: flutter run  (lists available devices)
```

## Known gaps

- **Android toolchain not installed** (`flutter doctor` reports no Android SDK) — the project's
  `android/` folder was generated, but building/running on an Android device or emulator needs
  Android Studio + SDK installed separately (https://flutter.dev/to/windows-android-setup).
  Also, the dev backend runs over plain HTTP — Android blocks cleartext traffic to non-localhost
  hosts by default on API 28+; a network security config exempting the dev host would be needed
  before this is actually tested on Android.
- **iOS** cannot be built from Windows at all (needs macOS + Xcode) — the `ios/` folder is
  generated for when that becomes available. Microphone/speech-recognition usage descriptions
  are already added to `Info.plist`.
- Currently verified working targets on this machine: **web** (Chrome) only. Mobile platform
  scope (Android-only vs Android+iOS, per `IMPLEMENTATION_PLAN.md`'s open decisions list) is
  still unconfirmed — all platform folders were kept since `flutter create` generates them by
  default; unused ones can be deleted once the scope is decided.
- **Auth is a device-bootstrapped placeholder**, not a real login screen (Phase 1's onboarding/
  consent/login screens still aren't built). `ApiClient` auto-registers a random per-device
  account on first use and stores tokens in `flutter_secure_storage`. There is no way yet to
  log into an existing account from a second device, and no consent screen is shown before use.
