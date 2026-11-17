// Live backend check for the Flutter auth client.
// Skipped unless LIVE_BACKEND_URL is provided, so the default suite stays offline.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:codingmatrix_desktop/infrastructure/auth/cloud_auth_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/authenticated_client.dart';
import 'package:codingmatrix_desktop/infrastructure/auth/credential_store.dart';
import 'package:codingmatrix_desktop/infrastructure/provider/provider_key_client.dart';
import 'package:codingmatrix_desktop/infrastructure/workflow/workflow_client.dart';

void main() {
  final baseUrl = Platform.environment['LIVE_BACKEND_URL'];
  final enabled = baseUrl != null && baseUrl.isNotEmpty;

  test('live login, authenticated headers and remote logout', () async {
    final client = CloudAuthClient(
      httpClient: http.Client(),
      credentialStore: CredentialStore(),
      baseUrl: baseUrl!,
    );
    final suffix = DateTime.now().microsecondsSinceEpoch;
    final email = 'flutter_live_$suffix@example.com';
    final password = 'LiveTest#2026xy';

    final csrf = await client.fetchCsrfToken();
    expect(csrf, isNotEmpty);

    // The client has no register endpoint; create the account through a raw
    // request that reuses the CSRF cookie already stored on the client.
    final register = http.Request(
      'POST',
      Uri.parse('$baseUrl/api/v1/register'),
    );
    register.headers['Content-Type'] = 'application/json';
    register.headers['X-CSRF-Token'] = csrf;
    register.headers['Cookie'] = 'csrf_token=$csrf';
    register.body = '{"username":"flutter_live_$suffix",'
        '"email":"$email","password":"$password"}';
    final registerResponse =
        await http.Response.fromStream(await client.httpClient.send(register));
    expect(registerResponse.statusCode, 200,
        reason: 'register failed: ${registerResponse.body}');

    final session = await client.login(email: email, password: password);
    expect(session.username, isNotEmpty);
    expect(client.session, isNotNull);

    final headers = await client.headers(
      Uri.parse('$baseUrl/api/v1/agent/host/sessions'),
      client.session!.accessTokenRef,
    );
    expect(headers['Authorization'], startsWith('Bearer '));
    expect(headers['X-CSRF-Token'], isNotNull);

    final probe = http.Request(
      'GET',
      Uri.parse('$baseUrl/api/v1/agent/host/sessions'),
    );
    probe.headers.addAll(headers);
    final probeResponse =
        await http.Response.fromStream(await client.httpClient.send(probe));
    expect(probeResponse.statusCode, 200,
        reason: 'authenticated request failed: ${probeResponse.body}');

    await client.logout(revokeRemote: true);
    expect(client.session, isNull);
    // Remote revocation depends on a Redis denylist. Without Redis the backend
    // fails open by design, so this test only asserts the client cleared its
    // local session; the backend logout call itself is covered by unit tests.
  }, skip: enabled ? false : 'set LIVE_BACKEND_URL to run against a live backend');

  test('workflow execute survives the server gzip mislabel', () async {
    final client = CloudAuthClient(
      httpClient: http.Client(),
      credentialStore: CredentialStore(),
      baseUrl: baseUrl!,
    );
    final suffix = DateTime.now().microsecondsSinceEpoch;
    final email = 'flutter_wf_$suffix@example.com';
    final password = 'LiveTest#2026xy';

    final csrf = await client.fetchCsrfToken();
    final register = http.Request(
      'POST',
      Uri.parse('$baseUrl/api/v1/register'),
    );
    register.headers['Content-Type'] = 'application/json';
    register.headers['X-CSRF-Token'] = csrf;
    register.headers['Cookie'] = 'csrf_token=$csrf';
    register.body = '{"username":"flutter_wf_$suffix",'
        '"email":"$email","password":"$password"}';
    final registerResponse =
        await http.Response.fromStream(await client.httpClient.send(register));
    expect(registerResponse.statusCode, 200,
        reason: 'register failed: ${registerResponse.body}');
    await client.login(email: email, password: password);

    final api = AuthenticatedClient(
      client,
      http.Client(),
      streamTimeout: const Duration(minutes: 2),
    );
    // Mirrors the reported case: the stream must yield parsed NDJSON events
    // instead of failing with "Filter error, bad data" before the first event.
    final stream = await WorkflowClient(api).execute('say hello', 60);
    final events = await stream
        .take(2)
        .toList()
        .timeout(const Duration(minutes: 2));
    expect(events, isNotEmpty);
    expect(events.first['event'], 'workflow_started');

    await client.logout(revokeRemote: true);
  }, skip: enabled ? false : 'set LIVE_BACKEND_URL to run against a live backend');

  test('provider key submit and list work for deepseek', () async {
    final client = CloudAuthClient(
      httpClient: http.Client(),
      credentialStore: CredentialStore(),
      baseUrl: baseUrl!,
    );
    final suffix = DateTime.now().microsecondsSinceEpoch;
    final email = 'flutter_ak_$suffix@example.com';
    final password = 'LiveTest#2026xy';

    final csrf = await client.fetchCsrfToken();
    final register = http.Request(
      'POST',
      Uri.parse('$baseUrl/api/v1/register'),
    );
    register.headers['Content-Type'] = 'application/json';
    register.headers['X-CSRF-Token'] = csrf;
    register.headers['Cookie'] = 'csrf_token=$csrf';
    register.body = '{"username":"flutter_ak_$suffix",'
        '"email":"$email","password":"$password"}';
    final registerResponse =
        await http.Response.fromStream(await client.httpClient.send(register));
    expect(registerResponse.statusCode, 200,
        reason: 'register failed: ${registerResponse.body}');
    await client.login(email: email, password: password);

    final api = AuthenticatedClient(client, http.Client());
    final keys = ProviderKeyClient(api);
    // Mirrors the reported flow: open provider settings, pick deepseek, submit.
    // Redis backs both the submit and the list, so this fails loudly if the
    // storage service is down instead of silently showing an empty page.
    final token = await keys.submit(
      key: 'sk-live-deepseek-1234567890',
      provider: 'deepseek',
      remark: 'live smoke',
    );
    expect(token, isNotEmpty);

    final listed = await keys.list();
    final saved = listed.firstWhere((item) => item.token == token);
    expect(saved.provider, 'deepseek');
    expect(saved.enabled, isTrue);

    await client.logout(revokeRemote: true);
  }, skip: enabled ? false : 'set LIVE_BACKEND_URL to run against a live backend');
}
