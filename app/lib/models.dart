/// Data from the engine (/analyze, /instruments, /categories) and the user's edits.
library;

class Candidate {
  Candidate({required this.instrument, required this.label, required this.category, required this.score,
      required this.source});

  factory Candidate.fromJson(Map<String, dynamic> j) => Candidate(
      instrument: j['instrument'] as String,
      label: j['label'] as String,
      category: j['category'] as String,
      score: (j['score'] as num).toDouble(),
      source: j['source'] as String);

  final String instrument;
  final String label;
  final String category;
  final double score;
  final String source;
}

class Instrument {
  Instrument(this.id, this.label, this.category);
  final String id;
  final String label;
  final String category;
}

class CategoryInfo {
  CategoryInfo({required this.id, required this.name, required this.zh, required this.colorIndex,
      required this.folder});
  final String id;
  final String name;
  final String zh;
  final int colorIndex;
  final String folder;

  /// How categories are shown in the UI: in capitals ("DRUMS", "BUS").
  String get label => name.toUpperCase();
}

/// Lists the front end needs besides the analysis itself.
class Catalog {
  Catalog({required this.categories, required this.instruments, required this.palette});

  final List<CategoryInfo> categories; // conventional session order, "other" last
  final List<Instrument> instruments;
  final List<int> palette; // ARGB colours, palette index 1 = palette[0]

  CategoryInfo category(String id) =>
      categories.firstWhere((c) => c.id == id, orElse: () => categories.firstWhere((c) => c.id == 'other'));

  Instrument? instrument(String id) {
    for (final i in instruments) {
      if (i.id == id) return i;
    }
    return null;
  }

  int color(int index) => palette[(index - 1).clamp(0, palette.length - 1)];

  static int parseHex(String hex) => 0xFF000000 | int.parse(hex.replaceFirst('#', ''), radix: 16);
}

enum Confidence { high, medium, low, none }

/// Where the row's name comes from; decides whether the "keep unrecognised words" switch
/// and duplicate numbering may change it.
enum NameSource { engine, instrument, typed, original }

Confidence parseConfidence(String s) =>
    Confidence.values.firstWhere((c) => c.name == s, orElse: () => Confidence.none);

/// One stem in the list. Fields from the engine are refreshed when the audio pass returns,
/// unless the user already edited the row.
class TrackRow {
  TrackRow(this.file);

  final String file;
  String originalName = '';
  // engine result
  String proposedName = ''; // unrecognised words and Pro Tools suffixes removed
  String proposedNameKeep = ''; // the same, keeping them
  List<String> unknownWords = [];
  String dawTail = ''; // "_04-01", "-TCEx_01" 
  String? engineInstrument;
  String engineCategory = 'other';
  Confidence confidence = Confidence.none;
  String stage = 'none';
  List<Candidate> candidates = [];
  List<String> modifiers = [];
  String? number;
  bool dawDefault = false;
  String prepared = ''; // name after clean-up and batch prefix/suffix removal
  Map<String, dynamic> stereo = {};
  bool audioPending = false;
  // user's choice (initialised from the engine)
  String name = ''; // chosen name before duplicate numbering (see AppState.finalName)
  NameSource nameSource = NameSource.engine;
  String? instrument;
  String category = 'other';
  int colorIndex = 55;
  bool colorOverridden = false;
  bool mono = false;
  bool edited = false;
  // after /apply
  Map<String, dynamic>? applyResult;

  String get stereoType => (stereo['type'] as String?) ?? '';
  String get stereoAction => (stereo['action'] as String?) ?? 'keep';
  bool get needsReview => !edited && (confidence == Confidence.low || confidence == Confidence.none);

  /// Score of the chosen instrument among the candidates (null when it is not one of them).
  double? get score {
    for (final c in candidates) {
      if (c.instrument == instrument) return c.score;
    }
    return null;
  }

  void updateFromEngine(Map<String, dynamic> j, Catalog catalog, {bool keepUnknown = false}) {
    originalName = j['original_name'] as String;
    proposedName = j['proposed_name'] as String;
    proposedNameKeep = (j['proposed_name_keep'] as String?) ?? proposedName;
    unknownWords = [for (final w in (j['unknown_words'] as List?) ?? const []) w as String];
    dawTail = (j['daw_tail'] as String?) ?? '';
    engineInstrument = j['instrument'] as String?;
    engineCategory = j['category'] as String;
    confidence = parseConfidence(j['confidence'] as String);
    stage = j['stage'] as String;
    candidates = [for (final c in j['candidates'] as List) Candidate.fromJson(c as Map<String, dynamic>)];
    modifiers = [for (final m in j['modifiers'] as List) m as String];
    number = j['number'] as String?;
    dawDefault = (j['layers']?['daw_default'] as bool?) ?? false;
    prepared = (j['layers']?['prepared'] as String?) ?? '';
    stereo = (j['stereo'] as Map<String, dynamic>?) ?? {};
    if (edited) return;
    name = keepUnknown ? proposedNameKeep : proposedName;
    nameSource = NameSource.engine;
    instrument = engineInstrument;
    category = engineCategory;
    if (!colorOverridden) colorIndex = catalog.category(category).colorIndex;
    mono = stereoAction != 'keep';
  }
}

/// Engine scores (dictionary match 1.0, text-model cosine, audio class probability) shown as a
/// whole percentage, clamped to 0–100 %.
String percent(double score) => '${(score.clamp(0.0, 1.0) * 100).round()}%';

/// Same rule as the engine (pipeline._name) for a name chosen from the candidates:
/// standard label + modifiers not already in it (+ unrecognised words) + instance number
/// (+ the Pro Tools suffix when kept).
String composeName(String label, List<String> modifiers, String? number,
    {bool dawDefault = false, List<String> unknown = const [], String tail = ''}) {
  final parts = [label];
  final words = label.toLowerCase().split(' ').toSet();
  for (final m in modifiers) {
    if (!words.contains(m.toLowerCase()) && !parts.contains(m)) parts.add(m);
  }
  parts.addAll(unknown);
  if (number != null && !dawDefault) parts.add(number);
  final t = tail.replaceFirst(RegExp(r'^[_\-. ]+'), '');
  if (t.isNotEmpty) parts.add(t);
  return parts.join(' ');
}

/// Gives every name that occurs more than once a running number, in list order:
/// "Lead Vocal" x2 -> "Lead Vocal 1", "Lead Vocal 2"; "Tom 2" x2 -> "Tom 2-1", "Tom 2-2".
/// Numbers already used by other names are skipped.
List<String> numberDuplicates(List<String> names) {
  final count = <String, int>{};
  for (final n in names) {
    count[n] = (count[n] ?? 0) + 1;
  }
  final taken = names.where((n) => count[n] == 1).toSet();
  final next = <String, int>{};
  final out = <String>[];
  for (final n in names) {
    if (count[n] == 1) {
      out.add(n);
      continue;
    }
    final sep = RegExp(r'\d$').hasMatch(n) ? '-' : ' ';
    var k = next[n] ?? 1;
    while (taken.contains('$n$sep$k')) {
      k++;
    }
    final name = '$n$sep$k';
    taken.add(name);
    next[n] = k + 1;
    out.add(name);
  }
  return out;
}

/// /tempo result: beats of the rhythm stems and what they say about the tempo.
class TempoInfo {
  TempoInfo(this.raw);
  final Map<String, dynamic> raw;

  double get bpm => (raw['bpm'] as num).toDouble(); // steady: the grid's BPM; else the average
  int get bpmRounded => raw['bpm_rounded'] as int;
  double get bpmMin => (raw['bpm_min'] as num).toDouble(); // slowest / fastest bar
  double get bpmMax => (raw['bpm_max'] as num).toDouble();
  bool get steady => raw['steady'] as bool;
  String get suggestedMode => raw['suggested_mode'] as String; // constant | variable
  int? get signatureBeats => raw['signature_beats'] as int?;
  int get beatCount => raw['beat_count'] as int;
  double get gridErrorMs => (raw['grid_error_ms'] as num).toDouble();
  String get sourceKind => raw['source_kind'] as String; // drums | rhythm | all
  List<String> get sources => [for (final s in raw['sources'] as List) s as String];
  double get duration => (raw['duration'] as num).toDouble();
  List<double> get beats => [for (final b in raw['beats'] as List) (b as num).toDouble()];
  List<double> get downbeats => [for (final b in raw['downbeats'] as List) (b as num).toDouble()];
}
