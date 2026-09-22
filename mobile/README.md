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

Phase 10: a "Sync Health Connect data" button (Android-only) reads real vitals from Google
Health Connect (`lib/services/health_connect_adapter.dart`) and syncs them to the backend
(`lib/services/health_sync_service.dart`, `POST /vitals/sync`). This is the first mobile feature
**verified live end-to-end on a real Android emulator**, not just against fakes or via curl —
see `docs/AI_PIPELINE.md` for the full transcript.

Verified: `flutter analyze` (clean), `flutter test` (5/5 passing — a widget test driving the
typed-text send path against a fake `ApiClient`, a app-boot smoke test, and unit tests for the
Health Connect adapter's unit conversion), `flutter build web` (succeeds), and — as of Phase 10
— `flutter build apk --release` (succeeds) installed and run on a real Android emulator. The
voice/STT path still has no automated test (no microphone harness in this environment) —
verified manually by confirming the equivalent typed-text flow passes and the backend endpoints
work end-to-end.

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

- **Android toolchain**: installed as of Phase 10 (Android SDK + platform-tools + an API 34
  emulator with Google Play/Health Connect — see `docs/AI_PIPELINE.md`). A real `flutter build
  apk --release` has been built, installed, and run on a real Android emulator. **Correction to
  an earlier version of this doc**: it previously assumed a network security config exemption
  would be needed for the dev backend's plain-HTTP cleartext traffic on API 28+; empirically, a
  release build reached `http://10.0.2.2:8000` (the Android emulator's host-loopback address)
  without one — the assumption was untested and turned out unnecessary, at least on this
  emulator/API level. Two real build issues *were* found and fixed getting this far: the
  `health` plugin needs `FlutterFragmentActivity` (`android/app/src/main/kotlin/.../
  MainActivity.kt`), and Kotlin's incremental compiler crashes when the pub-cache and project
  are on different Windows drive letters (worked around via `kotlin.incremental=false` in
  `android/gradle.properties`) — both detailed in `docs/AI_PIPELINE.md`.
- **iOS** cannot be built from Windows at all (needs macOS + Xcode) — the `ios/` folder is
  generated for when that becomes available. Microphone/speech-recognition usage descriptions
  are already added to `Info.plist`.
- Currently verified working targets on this machine: **web** (Chrome) and **Android**
  (emulator). Mobile platform scope (Android-only vs Android+iOS, per `IMPLEMENTATION_PLAN.md`'s
  open decisions list) is still unconfirmed.
- **Auth is a device-bootstrapped placeholder**, not a real login screen (Phase 1's onboarding/
  consent/login screens still aren't built). `ApiClient` auto-registers a random per-device
  account on first use and stores tokens in `flutter_secure_storage`. There is no way yet to
  log into an existing account from a second device, and no consent screen is shown before use.
  **Bug found and fixed in Phase 10**: the bootstrap email's placeholder domain was
  `@device.local`, which the backend's email validator rejects outright (`.local` is a reserved
  mDNS TLD) — this silently broke registration for any real device the whole time this scaffold
  existed, undetected until a real Android build actually exercised it. Now `@example.com`.
- **Health Connect (Phase 10)**: read-only, Android-only, manual sync via a button (no
  background/automatic sync). No automated test for the permission-denied/unavailable path.
