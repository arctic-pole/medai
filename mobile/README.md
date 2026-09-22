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

Phase 11 (superseded by Phase 12 below for how it's triggered): TTS playback support was added
— `lib/services/speech_playback_service.dart` (backed by `audioplayers`) plays audio fetched
from `POST /assessment/speech`. Synthesis happens server-side (`backend/app/providers/tts/`) —
this service is playback only. Barge-in: activating the mic always interrupts any audio
currently playing, before even checking whether STT is available.

Phase 12: `ConversationScreen` is now the **complete interface** — there is no separate "get
assessment" action. `POST /messages` itself returns a real validated Assessment once nothing
more is missing (`SendMessageResult.isAssessment`), rendered as a normal assistant message with
a Play control attached. A high-risk result (`assessmentStatus` `urgent`/`emergency`) triggers a
required, non-dismissible confirmation dialog (`ux.confirmation_required_when:
high_risk_recommendation_considered`) — tapping outside does not close it; only the "I
understand" button does. **Session persistence**: on launch, the screen calls
`GET /conversations` (already ordered newest-first) and resumes the most recent one — loading
its history via `GET /messages` — instead of always starting a new conversation
(`ux.session_auto_preserved`, `resume_previous_consultation`). A resumed conversation's
*historical* messages render as plain text; the Play button and confirmation dialog only apply
to a message received in the current live session, since whether a past reply was itself a
validated Assessment isn't persisted on the `Message` row.

Verified: `flutter analyze` (clean), `flutter test` (19/19 passing), `flutter build web`
(succeeds), and `flutter build apk --release` (succeeds, installed and run on a real Android
emulator, Phase 10). The voice/STT path still has no automated test (no microphone harness in
this environment) — verified manually by confirming the equivalent typed-text flow passes and
the backend endpoints work end-to-end. Phase 12's new tests (4, in
`conversation_screen_test.dart`): a new conversation is created only when none exists to resume;
an existing conversation is resumed with its history instead of recreated; the high-risk
confirmation dialog appears, resists tap-outside-to-dismiss, and is dismissed only by
"I understand"; a non-high-risk assessment shows no dialog. A debugging note for future
reference: `_init()`'s STT-availability check can hang indefinitely in the widget-test sandbox
(no platform channel mock), so anything that must render before that resolves — like resumed
message history — has to trigger its own `setState` rather than relying on a rebuild at the end
of `_init()`.

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
