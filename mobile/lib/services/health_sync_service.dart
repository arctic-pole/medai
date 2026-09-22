import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api_client.dart';
import 'health_connect_adapter.dart';

/// Result of one sync attempt — surfaced to the UI so a rejected reading is never silently
/// dropped from what the user sees, matching vital_system's "never silently drop" rule.
class HealthSyncResult {
  HealthSyncResult({required this.synced, required this.accepted, required this.rejected});
  final int synced;
  final int accepted;
  final int rejected;
}

/// Ties HealthConnectAdapter (reads real Health Connect data) to ApiClient (POSTs it to the
/// backend's VITAL_SERVICE at /vitals/sync). This is the app-side orchestration Phase 10 needs
/// on top of the adapter itself: registering a device once and reusing it, requesting
/// permissions, and turning DEVICE_ERROR into something the UI can show rather than a crash.
class HealthSyncService {
  HealthSyncService({ApiClient? apiClient, HealthConnectAdapter? adapter})
      : _apiClient = apiClient ?? ApiClient(),
        _adapter = adapter ?? HealthConnectAdapter();

  final ApiClient _apiClient;
  final HealthConnectAdapter _adapter;
  final _storage = const FlutterSecureStorage();
  static const _deviceIdKey = 'medai_health_connect_device_id';

  Future<String> _ensureDeviceId() async {
    final existing = await _storage.read(key: _deviceIdKey);
    if (existing != null) return existing;

    final deviceId = await _apiClient.registerDevice(deviceType: 'health_connect', label: 'Health Connect');
    await _storage.write(key: _deviceIdKey, value: deviceId);
    return deviceId;
  }

  /// Requests Health Connect permissions for every vital type this adapter reads. Returns
  /// false (rather than throwing) if the user denies them or Health Connect itself is
  /// unavailable — a normal, expected outcome the caller should let the user retry from, not
  /// treat as a crash.
  Future<bool> requestPermissions() async {
    try {
      return await _adapter.requestPermissions();
    } on HealthConnectUnavailable {
      return false;
    }
  }

  /// Reads recent Health Connect data and syncs it to the backend. Throws
  /// [HealthConnectUnavailable] if Health Connect itself can't be reached (surfaced to the UI
  /// as "please enter vitals manually", per vital_system.rules — never fabricated).
  Future<HealthSyncResult> sync({Duration lookback = const Duration(days: 7)}) async {
    final readings = await _adapter.readRecent(lookback: lookback);
    final deviceId = await _ensureDeviceId();

    final response = await _apiClient.syncVitals(
      deviceId: deviceId,
      readings: [for (final r in readings) r.toJson()],
    );

    return HealthSyncResult(
      synced: response['synced'] as int,
      accepted: response['accepted'] as int,
      rejected: response['rejected'] as int,
    );
  }
}
