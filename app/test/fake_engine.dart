import 'dart:convert';
import 'dart:io';

import 'package:stem_import/engine/engine_api.dart';
import 'package:stem_import/models.dart';

Map<String, dynamic> fixture(String name) =>
    jsonDecode(File('test/fixtures/$name').readAsStringSync()) as Map<String, dynamic>;

/// Engine stand-in built from real engine output (test/fixtures, exported from engine/ and the
/// M3 end-to-end run). Records what the app sends.
class FakeEngine implements EngineApi {
  FakeEngine({String analysis = 'analyze_m3.json'}) : _analysis = _load(analysis);

  static Map<String, dynamic> _load(String name) =>
      {for (final t in fixture(name)['tracks'] as List) (t as Map)['file'] as String: t};

  final analyzed = <String>[];
  // Failure injection. Each /session call takes the next entry: an EngineException to throw,
  // 'no_session' for Pro Tools without an open session; when empty, a normal session.
  final sessionQueue = <Object>[];
  Object? previewError;
  Object? applyError;
  Object? analyzeError; // thrown once by the next /analyze
  int sessionCalls = 0;
  final feedbacks = <(String, String)>[];
  final applied = <(List<Map<String, dynamic>>, bool)>[];
  final tempoRequests = <List<Map<String, dynamic>>>[];
  final tempoApplied = <Map<String, dynamic>>[];
  bool tempoAccepted = true; // false: the user cancelled Pro Tools' MIDI Import Options
  Object? tempoError; // thrown by every /tempo while set
  final calls = <String>[]; // order of the writing calls: 'apply' (tracks), 'tempo'
  final Map<String, dynamic> _analysis;

  List<String> get files => _analysis.keys.toList();

  // ---------------------------------------------------------------- models
  /// Sizes from the engine's manifest. Every model starts ready; tests set other states.
  static const modelSizes = {'qwen3_embedding': 1129773279, 'peav_audio': 221755759, 'beat_this': 82398145};
  static const modelLayers = {'qwen3_embedding': 'C', 'peav_audio': 'D', 'beat_this': 'T'};
  final modelStates = {for (final n in modelSizes.keys) n: _modelEntry(n, 'ready')};
  final downloads = <List<String>>[]; // every POST /models/download body
  int clearCalls = 0;
  Object? clearError; // thrown by DELETE /models while set (e.g. the 409)
  final modelsDir = '/Users/demo/Library/Application Support/TrackMate/models';

  static Map<String, dynamic> _modelEntry(String name, String state,
      {int bytesDone = -1, String? file, String? error, int onDisk = -1}) {
    final size = modelSizes[name]!;
    final done = bytesDone >= 0 ? bytesDone : (state == 'ready' ? size : 0);
    return {
      'name': name, 'layer': modelLayers[name], 'state': state, 'size': size, 'bytes_total': size,
      'bytes_done': done, 'progress': (done / size * 10000).round() / 10000, 'current_file': file,
      'error': error, 'on_disk': onDisk >= 0 ? onDisk : done, 'repo': 'aaatmy/$name',
    };
  }

  /// Puts [name] in [state]: 'missing', 'downloading' (at [progress], 0–1), 'error' or 'ready'.
  void setModel(String name, String state, {double progress = 0, String? file, String? error, int onDisk = -1}) {
    modelStates[name] = _modelEntry(name, state,
        bytesDone: (modelSizes[name]! * progress).round(), file: file, error: error, onDisk: onDisk);
  }

  Map<String, dynamic> _modelsAnswer() => {
        'layers': {
          'A': true, 'B': true,
          for (final e in modelLayers.entries) e.value: modelStates[e.key]!['state'] == 'ready',
        },
        'models': {for (final e in modelStates.entries) e.key: Map<String, dynamic>.of(e.value)},
        'dir': modelsDir,
      };

  @override
  Future<Map<String, dynamic>> models() async => _modelsAnswer();

  /// Like the engine: a missing or failed model starts downloading (here: stuck at 36 % of its
  /// first file until a test calls [setModel]); ready ones are skipped.
  @override
  Future<Map<String, dynamic>> downloadModels(List<String> names) async {
    downloads.add(List.of(names));
    for (final n in names) {
      if (modelStates[n]!['state'] != 'ready') setModel(n, 'downloading', progress: 0.36, file: 'onnx/model.onnx');
    }
    return _modelsAnswer();
  }

  @override
  Future<Map<String, dynamic>> clearModels() async {
    clearCalls++;
    if (clearError != null) throw clearError!;
    var freed = 0;
    for (final n in modelStates.keys.toList()) {
      freed += modelStates[n]!['on_disk'] as int;
      setModel(n, 'missing');
    }
    return {'freed_bytes': freed, ..._modelsAnswer()};
  }

  @override
  Future<List<Map<String, dynamic>>> analyze(List<String> files, {String audio = 'auto'}) async {
    final err = analyzeError;
    if (err != null) {
      analyzeError = null;
      throw err;
    }
    analyzed.add(audio);
    return [for (final f in files) _analysis[f]! as Map<String, dynamic>];
  }

  @override
  Future<void> feedback(String name, String instrument) async => feedbacks.add((name, instrument));

  @override
  Future<Catalog> catalog() async {
    final inst = fixture('instruments.json');
    final cats = fixture('categories.json');
    final names = {for (final c in inst['categories'] as List) c['id'] as String: c as Map<String, dynamic>};
    return Catalog(
      categories: [
        for (final e in (cats['categories'] as Map<String, dynamic>).entries)
          CategoryInfo(
              id: e.key,
              name: (names[e.key]?['name'] as String?) ?? 'Other',
              zh: (names[e.key]?['zh'] as String?) ?? '其他',
              colorIndex: (e.value as Map)['color_index'] as int,
              folder: (e.value as Map)['folder'] as String),
      ],
      instruments: [
        for (final i in inst['instruments'] as List) Instrument(i['id'] as String, i['label'] as String, i['category'] as String),
      ],
      palette: [for (final c in cats['palette'] as List) Catalog.parseHex(c as String)],
    );
  }

  @override
  Future<Map<String, dynamic>> session() async {
    sessionCalls++;
    if (sessionQueue.isNotEmpty) {
      final next = sessionQueue.removeAt(0);
      if (next is EngineException) throw next;
      if (next == 'no_session') return {'connected': true, 'session': null, 'tracks': []};
    }
    return {
      'connected': true,
      'session': {'name': 'Demo Session', 'path': '/tmp/Demo.ptx', 'sample_rate': 48000},
      'tracks': [],
    };
  }

  @override
  Future<Map<String, dynamic>> apply(List<Map<String, dynamic>> tracks, {bool dryRun = false}) async {
    if (dryRun && previewError != null) throw previewError!;
    if (!dryRun && applyError != null) throw applyError!;
    applied.add((tracks, dryRun));
    if (!dryRun) calls.add('apply');
    final plan = [
      {
        'folder': 'ALL', 'category': 'drums', 'color_index': 8, 'exists': false,
        'tracks': [for (final t in tracks) {'final_name': t['name'], 'color_index': t['color_index'], 'mono': t['mono']}],
      },
    ];
    if (dryRun) return {'session': (await session())['session'], 'dry_run': true, 'plan': plan, 'ok': true};
    return {
      'session': (await session())['session'], 'dry_run': false, 'plan': plan, 'ok': true, 'seconds': 1.5,
      'results': [
        for (final t in tracks)
          {'file': t['file'], 'final_name': t['name'], 'pt_name': t['name'], 'folder': 'ALL',
           'name_ok': true, 'folder_ok': true, 'color_ok': true, 'errors': []},
      ],
    };
  }

  /// Real /tempo output (85 BPM, steady) with the sources renamed to the fake's drum stems.
  @override
  Future<Map<String, dynamic>> tempo(List<Map<String, dynamic>> tracks) async {
    tempoRequests.add(tracks);
    if (tempoError != null) throw tempoError!;
    return fixture('tempo.json');
  }

  @override
  Future<Map<String, dynamic>> applyTempo(Map<String, dynamic> request) async {
    tempoApplied.add(request);
    calls.add('tempo');
    final constant = request['mode'] == 'constant';
    final name = constant ? 'TrackMate Tempo ${request['bpm']} BPM.mid' : 'TrackMate Tempo Map (avg 85 BPM).mid';
    final toPt = request['import_to_pro_tools'] == true;
    return {
      'midi_path': '${request['folder']}/$name', 'mode': request['mode'], 'bpm': constant ? request['bpm'] : 85.0,
      'beats_per_bar': 4, 'tempo_events': constant ? 1 : 88, 'imported': toPt, 'applied': toPt && tempoAccepted,
      if (toPt) 'pro_tools_position': tempoAccepted ? '   91| 1| 027' : '   73| 2| 400',
    };
  }
}
