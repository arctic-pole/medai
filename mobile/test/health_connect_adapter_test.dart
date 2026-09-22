import 'package:flutter_test/flutter_test.dart';
import 'package:medai/services/health_connect_adapter.dart';

void main() {
  group('convertHealthConnectValue', () {
    test('converts body temperature from Celsius to Fahrenheit', () {
      // 37.0C is normal body temperature, ~98.6F — the backend's canonical unit.
      expect(convertHealthConnectValue('body_temperature', 37.0), closeTo(98.6, 0.01));
    });

    test('leaves other vital types unchanged (already in the backend-expected unit)', () {
      expect(convertHealthConnectValue('heart_rate', 72.0), 72.0);
      expect(convertHealthConnectValue('oxygen_saturation', 85.0), 85.0);
      expect(convertHealthConnectValue('blood_pressure_systolic', 120.0), 120.0);
      expect(convertHealthConnectValue('weight', 70.0), 70.0);
    });
  });

  group('HealthConnectReading.toJson', () {
    test('serializes with an ISO-8601 UTC timestamp matching backend/app/schemas/vital.py', () {
      final reading = HealthConnectReading(
        type: 'heart_rate',
        value: 72.0,
        unit: 'bpm',
        timestamp: DateTime.utc(2026, 6, 1, 12, 30),
      );
      final json = reading.toJson();
      expect(json['type'], 'heart_rate');
      expect(json['value'], 72.0);
      expect(json['unit'], 'bpm');
      expect(json['timestamp'], '2026-06-01T12:30:00.000Z');
    });
  });
}
