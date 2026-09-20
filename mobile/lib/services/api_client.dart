import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

/// Talks to the MEDAI backend (see backend/app/api/*.py).
///
/// Phase 1's real auth/onboarding screens aren't built yet (see mobile/README.md), so this
/// bootstraps a per-device account automatically on first use: no login form, no typed
/// credentials — consistent with ux.user_must_not_be_required_to. This is temporary scaffolding
/// for testing the Phase 2 conversation pipeline, not a real authentication UX; it is replaced
/// once Phase 1's mobile screens (consent, onboarding, login) are built.
class ApiClient {
  ApiClient({String? baseUrl}) : baseUrl = baseUrl ?? _defaultBaseUrl;

  // Android emulators reach the host machine at 10.0.2.2, not localhost. Web/desktop use
  // localhost directly. Override via ApiClient(baseUrl: ...) for a real device/deployment.
  static const _defaultBaseUrl = 'http://localhost:8000';

  final String baseUrl;
  final _storage = const FlutterSecureStorage();
  static const _accessTokenKey = 'medai_access_token';
  static const _refreshTokenKey = 'medai_refresh_token';
  static const _deviceEmailKey = 'medai_device_email';

  Future<String> _ensureAccessToken() async {
    final existing = await _storage.read(key: _accessTokenKey);
    if (existing != null) return existing;
    return _bootstrapDeviceAccount();
  }

  Future<String> _bootstrapDeviceAccount() async {
    var email = await _storage.read(key: _deviceEmailKey);
    final password = const Uuid().v4();

    if (email == null) {
      email = 'device-${const Uuid().v4()}@device.local';
      await _storage.write(key: _deviceEmailKey, value: email);
    }

    final response = await http.post(
      Uri.parse('$baseUrl/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode != 201) {
      throw ApiException('failed to bootstrap device account: ${response.statusCode} ${response.body}');
    }

    final tokens = jsonDecode(response.body) as Map<String, dynamic>;
    await _storage.write(key: _accessTokenKey, value: tokens['access_token'] as String);
    await _storage.write(key: _refreshTokenKey, value: tokens['refresh_token'] as String);
    return tokens['access_token'] as String;
  }

  Future<Map<String, String>> _authHeaders() async {
    final token = await _ensureAccessToken();
    return {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'};
  }

  Future<String> createConversation() async {
    final response = await http.post(Uri.parse('$baseUrl/conversations'), headers: await _authHeaders());
    if (response.statusCode != 201) {
      throw ApiException('failed to create conversation: ${response.statusCode} ${response.body}');
    }
    return (jsonDecode(response.body) as Map<String, dynamic>)['id'] as String;
  }

  /// Sends [content] as a user message and returns the assistant's (Phase 2: scaffold) reply.
  Future<String> sendMessage({required String conversationId, required String content}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/messages'),
      headers: await _authHeaders(),
      body: jsonEncode({'conversation_id': conversationId, 'content': content}),
    );
    if (response.statusCode != 201) {
      throw ApiException('failed to send message: ${response.statusCode} ${response.body}');
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return (body['assistant_message'] as Map<String, dynamic>)['content'] as String;
  }
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => 'ApiException: $message';
}
