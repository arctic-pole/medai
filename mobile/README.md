# MEDAI Mobile

A Flutter app. Scaffolded via `flutter create --org com.medai --project-name medai .`.

## Status

Phase 0 placeholder screen in place (`lib/main.dart` → `lib/screens/home_screen.dart`), verified
with `flutter analyze` (clean), `flutter test` (passing), and `flutter build web` (succeeds).

Proposed layout, filled in as later phases land (see `IMPLEMENTATION_PLAN.md`):

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
- **iOS** cannot be built from Windows at all (needs macOS + Xcode) — the `ios/` folder is
  generated for when that becomes available.
- Currently verified working targets on this machine: **web** (Chrome) only. Mobile platform
  scope (Android-only vs Android+iOS, per `IMPLEMENTATION_PLAN.md`'s open decisions list) is
  still unconfirmed — all platform folders were kept since `flutter create` generates them by
  default; unused ones can be deleted once the scope is decided.
