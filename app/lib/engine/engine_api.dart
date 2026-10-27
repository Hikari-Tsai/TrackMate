import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models.dart';

/// An engine error. [code] is the engine's stable error code (`pro_tools_not_running`,
/// `no_session`, `pro_tools_not_responding`, `pro_tools_lost`, `missing_files`, …) or
/// `engine_unreachable` when the engine itself does not answer.
class EngineException implements Exception {
  EngineException(this.status, this.message, {this.code = '', this.files = const []});
  final int status;
  final String message;
  final String code;
  final List<String> files;
  @override
  String toString() => 'EngineException($status, $code): $message';
}

/// The engine's HTTP API (engine/README.md). Abstract so tests can use a fake.
abstract class EngineApi {
  Future<Map<String, dynamic>> models();
  Future<List<Map<String, dynamic>>> analyze(List<String> files, {String audio = 'auto'});
  Future<void> feedback(String name, String instrument);
  Future<Catalog> catalog();
  Future<Map<String, dynamic>> session();
  Future<Map<String, dynamic>> apply(List<Map<String, dynamic>> tracks, {bool dryRun = false});
}

class HttpEngineApi implements EngineApi {
  HttpEngineApi(this.base, this.token, {http.Client? client}) : _client = client ?? http.Client();

  final Uri base;
  final String token;
  final http.Client _client;

  Map<String, String> get _headers => {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'};

  Future<dynamic> _send(String method, String path, [Object? body]) async {
    final uri = base.resolve(path);
    final http.Response res;
    try {
      res = method == 'GET'
          ? await _client.get(uri, headers: _headers)
          : await _client.post(uri, headers: _headers, body: jsonEncode(body ?? {}));
    } on SocketException catch (e) {
      throw EngineException(0, 'The engine does not answer ($e)', code: 'engine_unreachable');
    } on http.ClientException catch (e) {
      throw EngineException(0, 'The engine does not answer ($e)', code: 'engine_unreachable');
    }
    final text = utf8.decode(res.bodyBytes);
    if (res.statusCode != 200) {
      Object? detail = text;
      try {
        detail = (jsonDecode(text) as Map)['detail'];
      } catch (_) {}
      if (detail is Map) {
        throw EngineException(res.statusCode, '${detail['message'] ?? detail}',
            code: '${detail['code'] ?? ''}',
            files: [for (final f in (detail['missing_files'] as List?) ?? const []) '$f']);
      }
      throw EngineException(res.statusCode, '$detail');
    }
    return jsonDecode(text);
  }

  Future<bool> health() async {
    try {
      final res = await _client.get(base.resolve('/health'));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<Map<String, dynamic>> models() async => (await _send('GET', '/models')) as Map<String, dynamic>;

  @override
  Future<List<Map<String, dynamic>>> analyze(List<String> files, {String audio = 'auto'}) async {
    final res = await _send('POST', '/analyze', {'files': files, 'audio': audio}) as Map<String, dynamic>;
    return [for (final t in res['tracks'] as List) t as Map<String, dynamic>];
  }

  @override
  Future<void> feedback(String name, String instrument) =>
      _send('POST', '/feedback', {'name': name, 'instrument': instrument});

  @override
  Future<Catalog> catalog() async {
    final inst = await _send('GET', '/instruments') as Map<String, dynamic>;
    final cats = await _send('GET', '/categories') as Map<String, dynamic>;
    final names = {for (final c in inst['categories'] as List) c['id'] as String: c as Map<String, dynamic>};
    final spec = cats['categories'] as Map<String, dynamic>;
    return Catalog(
      categories: [
        for (final e in spec.entries)
          CategoryInfo(
            id: e.key,
            name: (names[e.key]?['name'] as String?) ?? 'Other',
            zh: (names[e.key]?['zh'] as String?) ?? '',
            colorIndex: (e.value as Map)['color_index'] as int,
            folder: (e.value as Map)['folder'] as String,
          ),
      ],
      instruments: [
        for (final i in inst['instruments'] as List)
          Instrument(i['id'] as String, i['label'] as String, i['category'] as String),
      ],
      palette: [for (final c in cats['palette'] as List) Catalog.parseHex(c as String)],
    );
  }

  @override
  Future<Map<String, dynamic>> session() async => (await _send('GET', '/session')) as Map<String, dynamic>;

  @override
  Future<Map<String, dynamic>> apply(List<Map<String, dynamic>> tracks, {bool dryRun = false}) async =>
      (await _send('POST', '/apply', {'tracks': tracks, 'dry_run': dryRun})) as Map<String, dynamic>;
}
