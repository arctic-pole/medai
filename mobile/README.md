# MEDAI Mobile — Phase 0 blocker

Per `IMPLEMENTATION_PLAN.md` (Phase 0), the mobile app is a Flutter project. The Flutter SDK
is **not installed** in the environment this scaffold was created in, so `flutter create .`
could not be run here.

**Blocker, reported per `medai_spec.yaml` `agent_rules.change_control`** ("If a requirement
cannot be implemented: STOP and report the blocker."):

To unblock Phase 0's mobile skeleton, install the Flutter SDK
(https://docs.flutter.dev/get-started/install) and run, from this `mobile/` directory:

```
flutter create --org com.medai --project-name medai .
```

This will scaffold the standard Flutter project layout (`lib/`, `android/`, `ios/`, `test/`,
`pubspec.yaml`, etc.) in place. After that, add the screens under `lib/screens/` per
`ux.screens` in `medai_spec.yaml`, and an API client + audio capture/playback service under
`lib/services/`, per the layout proposed in `IMPLEMENTATION_PLAN.md`.

Also still open per the plan's consolidated decisions list: **target mobile platforms**
(Android only vs Android + iOS) — confirm before running `flutter create`, since it affects
which platform folders are generated/kept and which CI jobs are meaningful (iOS builds require
a macOS runner).
