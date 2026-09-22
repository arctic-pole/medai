package com.medai.medai

// Phase 10: the `health` plugin (Health Connect) casts the attached Activity to a
// FragmentActivity when requesting permissions -- verified against its own example app
// (health-13.3.2/example/android/.../MainActivity.kt) after a ClassCastException on plain
// FlutterActivity. FlutterFragmentActivity is a drop-in superset, so this doesn't affect any
// other plugin already in use (speech_to_text, flutter_secure_storage).
import io.flutter.embedding.android.FlutterFragmentActivity

class MainActivity : FlutterFragmentActivity()
