import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'alerts.dart';
import 'engine/engine_api.dart';
import 'models.dart';

/// File name of a path with either separator (macOS '/', Windows '\\').
String baseName(String path) => path.split(RegExp(r'[\\/]')).last;

const audioExtensions = {'.wav', '.wave', '.aif', '.aiff', '.mp3', '.flac', '.m4a', '.ogg', '.caf'};

enum EngineState { starting, ready, error }

/// Everything the screen shows. Adding files runs /analyze twice: first with the text layers
/// only (instant), then with the audio layer for the tracks the text could not settle.
class AppState extends ChangeNotifier {
  AppState();

  EngineApi? api;
  EngineState engineState = EngineState.starting;
  String? engineError;
  Catalog? catalog;
  Map<String, bool> layers = {};
  Map<String, dynamic> models = {};
  Map<String, dynamic>? session; // /session result, null until read
  String? sessionError; // short text for the session bar
  EngineException? sessionException; // why the last /session failed
  final _alerts = StreamController<AppAlert>.broadcast();

  /// Problems the screen shows as dialogs (no audio files, engine stopped, recognition failed).
  Stream<AppAlert> get alerts => _alerts.stream;

  /// Set by the app: stops and starts the engine process again.
  Future<void> Function()? restartEngine;

  void alert(AppAlert a) => _alerts.add(a);

  /// Called before restarting the engine: the list stays, the engine status resets.
  void engineRestarting() {
    engineState = EngineState.starting;
    engineError = null;
    notifyListeners();
  }
  final List<TrackRow> tracks = [];
  bool busy = false;
  String? message;
  bool dragHover = false;
  /// Keep words nothing recognised and Pro Tools suffixes ("_04-01", "-TCEx_01") in names.
  /// Off by default: they are removed.
  bool keepUnknown = false;
  Timer? _modelTimer;

  Future<void> attach(EngineApi engine) async {
    api = engine;
    try {
      catalog = await engine.catalog();
      await refreshModels();
      engineState = EngineState.ready;
      unawaited(refreshSession());
    } catch (e) {
      engineState = EngineState.error;
      engineError = '$e';
    }
    notifyListeners();
  }

  void setDragHover(bool on) {
    if (dragHover == on) return;
    dragHover = on;
    notifyListeners();
  }

  void fail(Object error) {
    engineState = EngineState.error;
    engineError = '$error';
    notifyListeners();
  }

  Future<void> refreshModels() async {
    final m = await api!.models();
    layers = {for (final e in (m['layers'] as Map).entries) e.key as String: e.value as bool};
    models = m['models'] as Map<String, dynamic>;
    if (tempoModelReady && tempoError?.code == 'tempo_model_not_ready' && !busy) unawaited(detectTempo(again: true));
    final downloading = models.values.any((s) => (s as Map)['state'] == 'downloading');
    _modelTimer?.cancel();
    if (downloading) {
      _modelTimer = Timer(const Duration(seconds: 2), () => refreshModels().then((_) => notifyListeners()));
    }
  }

  Future<void> refreshSession() async {
    try {
      session = await api!.session();
      sessionError = null;
      sessionException = null;
    } on EngineException catch (e) {
      session = null;
      sessionException = e;
      sessionError = switch (e.code) {
        'pro_tools_not_running' => 'Pro Tools is not running',
        'pro_tools_not_responding' => 'Pro Tools is not responding',
        'engine_unreachable' => 'Engine is not answering',
        _ => e.message,
      };
    }
    notifyListeners();
  }

  /// Why applying cannot start now, or null when Pro Tools has an open session.
  AppAlert? get sessionProblem {
    if (sessionException != null) return AppAlert.fromError(sessionException!);
    if (session?['session'] == null) {
      return AppAlert.fromError(EngineException(409, 'No session', code: 'no_session'));
    }
    return null;
  }

  // ------------------------------------------------------------------ files
  /// Expands folders, keeps audio files, skips files already in the list.
  static List<String> collectAudio(List<String> paths) {
    final out = <String>[];
    for (final p in paths) {
      if (FileSystemEntity.isDirectorySync(p)) {
        final files = Directory(p).listSync(recursive: true).whereType<File>().map((f) => f.path).toList()..sort();
        out.addAll(files.where(_isAudio));
      } else if (_isAudio(p)) {
        out.add(p);
      }
    }
    return out;
  }

  static bool _isAudio(String p) {
    final dot = p.lastIndexOf('.');
    final name = baseName(p);
    return dot > 0 && !name.startsWith('.') && audioExtensions.contains(p.substring(dot).toLowerCase());
  }

  Future<void> addFiles(List<String> paths) async {
    if (paths.isEmpty || api == null || catalog == null) return;
    final audio = collectAudio(paths);
    if (audio.isEmpty) {
      alert(AppAlert.noAudioFiles);
      return;
    }
    final known = tracks.map((t) => t.file).toSet();
    final files = audio.where((f) => !known.contains(f)).toList();
    if (files.isEmpty) {
      message = 'These files are already in the list';
      notifyListeners();
      return;
    }
    final rows = [for (final f in files) TrackRow(f)..originalName = baseName(f)];
    tracks.addAll(rows);
    _forgetTempo();
    await _analyse(rows);
  }

  Future<void> _analyse(List<TrackRow> rows) async {
    busy = true;
    message = 'Recognising ${rows.length} file${rows.length == 1 ? '' : 's'}…';
    notifyListeners();
    try {
      // The whole list goes to the engine so batch prefixes (song titles) are found.
      final all = tracks.map((t) => t.file).toList();
      final text = await api!.analyze(all, audio: 'none');
      _merge(text);
      final pending = rows.where((r) => r.stage == 'none' || r.confidence == Confidence.low).toList();
      if (pending.isNotEmpty && (layers['D'] ?? false)) {
        for (final r in pending) {
          r.audioPending = true;
        }
        message = 'Listening to ${pending.length} track${pending.length == 1 ? '' : 's'}…';
        notifyListeners();
        final audio = await api!.analyze(all, audio: 'auto');
        for (final r in pending) {
          r.audioPending = false;
        }
        _merge(audio);
      }
      message = null;
      unawaited(detectTempo()); // in the background while the user reviews the names
    } catch (e) {
      for (final r in rows) {
        r.audioPending = false;
      }
      busy = false;
      if (e is EngineException && e.code == 'missing_files') {
        // Drop the files that are gone and analyse the rest again.
        tracks.removeWhere((t) => e.files.contains(t.file));
        rows = rows.where((r) => !e.files.contains(r.file)).toList();
        alert(AppAlert.fromError(e));
        if (rows.isNotEmpty) return _analyse(rows);
      } else {
        alert(AppAlert.fromError(e, doing: 'recognise the files'));
      }
      message = 'Recognition stopped';
    }
    busy = false;
    notifyListeners();
  }

  void _merge(List<Map<String, dynamic>> results) {
    final byFile = {for (final r in results) r['file'] as String: r};
    for (final row in tracks) {
      final r = byFile[row.file];
      if (r != null) row.updateFromEngine(r, catalog!, keepUnknown: keepUnknown);
    }
  }

  // ------------------------------------------------------------------ edits
  /// Choose an instrument (from the Top-5 or the full search). A choice other than the
  /// engine's Top-1 is sent to /feedback so layer A knows this name next time. The alias is
  /// the name without the song title ("synth pad", not "mysong synth pad"), and DAW default
  /// names ("Audio 3") are never learnt: they say nothing about the instrument.
  /// Name for an instrument chosen from the menu, following the keep-unrecognised switch.
  String _nameFor(TrackRow row, String label) => composeName(label, row.modifiers, row.number,
      dawDefault: row.dawDefault,
      unknown: keepUnknown ? row.unknownWords : const [],
      tail: keepUnknown ? row.dawTail : '');

  void setKeepUnknown(bool keep) {
    if (keep == keepUnknown) return;
    keepUnknown = keep;
    for (final row in tracks) {
      switch (row.nameSource) {
        case NameSource.engine:
          row.name = keep ? row.proposedNameKeep : row.proposedName;
        case NameSource.instrument:
          final inst = row.instrument == null ? null : catalog!.instrument(row.instrument!);
          if (inst != null) row.name = _nameFor(row, inst.label);
        case NameSource.typed:
        case NameSource.original:
          break; // the user's own text is never changed
      }
    }
    notifyListeners();
  }

  /// Names as they will be sent to Pro Tools: the chosen name, with a running number when the
  /// same name appears more than once in the list.
  Map<TrackRow, String> get finalNames {
    final numbered = numberDuplicates([for (final t in tracks) t.name]);
    return {for (var i = 0; i < tracks.length; i++) tracks[i]: numbered[i]};
  }

  String finalName(TrackRow row) => finalNames[row] ?? row.name;

  void chooseInstrument(TrackRow row, String instrumentId) {
    final inst = catalog!.instrument(instrumentId);
    if (inst == null) return;
    row
      ..instrument = inst.id
      ..name = _nameFor(row, inst.label)
      ..nameSource = NameSource.instrument
      ..edited = true;
    _setCategory(row, inst.category);
    if (inst.id != row.engineInstrument && !row.dawDefault && row.prepared.isNotEmpty) {
      unawaited(api!.feedback(row.prepared, inst.id).catchError((_) {}));
    }
    notifyListeners();
  }

  void keepOriginalName(TrackRow row) {
    row
      ..name = row.originalName.replaceFirst(RegExp(r'\.[A-Za-z0-9]+$'), '')
      ..nameSource = NameSource.original
      ..edited = true;
    notifyListeners();
  }

  void rename(TrackRow row, String name) {
    final v = name.trim();
    // The field shows the numbered name; leaving it unchanged is not a rename.
    if (v.isEmpty || v == row.name || v == finalName(row)) return;
    row
      ..name = v
      ..nameSource = NameSource.typed
      ..edited = true;
    notifyListeners();
  }

  void setCategory(TrackRow row, String category) {
    _setCategory(row, category);
    row.edited = true;
    notifyListeners();
  }

  void _setCategory(TrackRow row, String category) {
    row.category = category;
    if (!row.colorOverridden) row.colorIndex = catalog!.category(category).colorIndex;
  }

  void setColor(TrackRow row, int colorIndex) {
    row
      ..colorIndex = colorIndex
      ..colorOverridden = true
      ..edited = true;
    notifyListeners();
  }

  void setMono(TrackRow row, bool mono) {
    row
      ..mono = mono
      ..edited = true;
    notifyListeners();
  }

  void remove(TrackRow row) {
    tracks.remove(row);
    _forgetTempo();
    notifyListeners();
    if (tracks.isNotEmpty && !busy) unawaited(detectTempo());
  }

  void clear() {
    tracks.clear();
    message = null;
    _forgetTempo();
    notifyListeners();
  }

  // ------------------------------------------------------------------ apply
  List<Map<String, dynamic>> _payload() {
    final names = finalNames;
    return [
      for (final t in tracks)
        {'file': t.file, 'name': names[t], 'category': t.category, 'color_index': t.colorIndex, 'mono': t.mono},
    ];
  }

  Future<Map<String, dynamic>> preview() => api!.apply(_payload(), dryRun: true);

  Future<Map<String, dynamic>> applyToProTools() async {
    busy = true;
    message = 'Applying to Pro Tools…';
    notifyListeners();
    try {
      final res = await api!.apply(_payload());
      final byFile = {for (final r in res['results'] as List) (r as Map)['file'] as String: r};
      for (final t in tracks) {
        t.applyResult = byFile[t.file] as Map<String, dynamic>?;
      }
      message = res['ok'] == true
          ? 'Applied ${tracks.length} tracks in ${res['seconds']} s'
          : 'Applied, but some tracks did not pass verification';
      unawaited(refreshSession());
      return res;
    } catch (e) {
      message = 'Apply stopped';
      rethrow;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  // ------------------------------------------------------------------ tempo
  // Detected automatically once the stems are recognised. Preview & apply always asks how to set
  // it (constant, tempo map, or keep the session tempo) and imports it right after the tracks.
  TempoInfo? tempo; // null until detected
  EngineException? tempoError; // why the last detection gave no tempo (no beat, model missing)
  bool tempoBusy = false; // detecting, or importing into Pro Tools
  String tempoMode = 'constant'; // constant | variable (tempo map) | none (keep the session tempo)
  double tempoFactor = 1; // 0.5 or 2 when the beat was heard in double or half time
  int tempoBpm = 120; // the constant tempo to set; starts at the rounded average
  Map<String, dynamic>? tempoResult; // last /tempo/apply
  String? _tempoInput; // the files and categories the current result was detected from
  Future<void>? _tempoJob;

  bool get tempoModelReady => layers['T'] ?? false;

  String get _tempoKey => [for (final t in tracks) '${t.file}\t${t.category}'].join('\n');

  /// Average BPM after half/double time.
  double get tempoAverage => (tempo?.bpm ?? 0) * tempoFactor;

  /// Whether Preview & apply will set the tempo.
  bool get tempoWillImport => tempo != null && tempoMode != 'none';

  /// What the header shows: the constant BPM, or the average of the map.
  String get tempoLabel => tempo == null
      ? ''
      : tempoMode == 'constant'
          ? '$tempoBpm BPM'
          : tempoMode == 'variable'
              ? '≈ ${tempoAverage.round()} BPM'
              : '${tempoAverage.round()} BPM';

  void _forgetTempo() {
    tempo = null;
    tempoError = null;
    tempoResult = null;
    _tempoInput = null;
  }

  /// Detects the tempo of the current list, unless that was already done for these files and
  /// categories ([again] repeats it). Errors are kept in [tempoError], not shown as alerts: the
  /// detection runs on its own and the tempo step of Preview & apply explains them.
  Future<void> detectTempo({bool again = false}) async {
    if (api == null || tracks.isEmpty) return;
    if (_tempoJob != null) {
      await _tempoJob; // the list may have changed meanwhile: check again
      return detectTempo(again: again);
    }
    if (!again && _tempoInput == _tempoKey) return;
    if (!tempoModelReady) {
      tempo = null;
      tempoError = EngineException(503, 'The tempo model is still downloading.', code: 'tempo_model_not_ready');
      notifyListeners();
      return; // tried again when the download finishes (refreshModels)
    }
    final key = _tempoKey;
    _tempoJob = () async {
      tempoBusy = true;
      tempoResult = null;
      notifyListeners();
      try {
        final res = await api!.tempo([for (final t in tracks) {'file': t.file, 'category': t.category}]);
        tempo = TempoInfo(res);
        tempoError = null;
        tempoFactor = 1;
        tempoMode = tempo!.suggestedMode;
        tempoBpm = tempo!.bpmRounded;
      } on EngineException catch (e) {
        tempo = null;
        tempoError = e;
      } catch (e) {
        tempo = null;
        tempoError = EngineException(0, '$e');
      } finally {
        _tempoInput = key;
        tempoBusy = false;
        notifyListeners();
      }
    }();
    try {
      await _tempoJob;
    } finally {
      _tempoJob = null;
    }
  }

  void setTempoMode(String mode) {
    tempoMode = mode;
    notifyListeners();
  }

  /// Half or double time. The constant BPM follows.
  void setTempoFactor(double factor) {
    tempoFactor = factor;
    tempoBpm = tempoAverage.round();
    notifyListeners();
  }

  void setTempoBpm(int bpm) {
    tempoBpm = bpm.clamp(20, 400);
    notifyListeners();
  }

  /// Writes the tempo MIDI next to the stems and imports it: Pro Tools then shows its MIDI
  /// Import Options dialog and the call returns when the user closes it.
  Future<Map<String, dynamic>> applyTempo() async {
    final t = tempo!;
    tempoBusy = true;
    message = 'Waiting for Pro Tools: press OK in "MIDI Import Options"';
    notifyListeners();
    try {
      final res = await api!.applyTempo({
        'beats': t.beats,
        'downbeats': t.downbeats,
        'duration': t.duration,
        'signature_beats': t.signatureBeats,
        'mode': tempoMode,
        'bpm': tempoMode == 'constant' ? tempoBpm : null,
        'factor': tempoFactor == 0.5 ? 0.5 : tempoFactor.toInt(),
        'folder': t.sources.isEmpty ? null : File(t.sources.first).parent.path,
        'import_to_pro_tools': true,
      });
      tempoResult = res;
      message = res['applied'] == true ? 'Pro Tools tempo set: $tempoLabel' : 'Pro Tools did not change its tempo';
      return res;
    } catch (e) {
      message = 'Tempo import stopped';
      rethrow;
    } finally {
      tempoBusy = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _alerts.close();
    _modelTimer?.cancel();
    super.dispose();
  }
}
