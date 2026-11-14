import 'dart:async';

import 'package:stem_import/player.dart';

/// Player stand-in: records the calls and lets a test send the events a real player would
/// (duration known, position ticks, state changes, the end of the file).
class FakePlayer implements StemPlayer {
  final calls = <String>[]; // 'play <file>', 'resume', 'pause', 'seek <ms>', 'stop'
  Object? playError; // thrown by the next play() while set
  final _positions = StreamController<Duration>.broadcast(sync: true);
  final _durations = StreamController<Duration>.broadcast(sync: true);
  final _statuses = StreamController<PlayerStatus>.broadcast(sync: true);

  String? get loaded {
    for (final c in calls.reversed) {
      if (c.startsWith('play ')) return c.substring(5);
    }
    return null;
  }

  @override
  Future<void> play(String file) async {
    calls.add('play $file');
    final e = playError;
    if (e != null) {
      playError = null;
      throw e;
    }
    _statuses.add(PlayerStatus.playing);
  }

  @override
  Future<void> resume() async {
    calls.add('resume');
    _statuses.add(PlayerStatus.playing);
  }

  @override
  Future<void> pause() async {
    calls.add('pause');
    _statuses.add(PlayerStatus.paused);
  }

  @override
  Future<void> seek(Duration position) async => calls.add('seek ${position.inMilliseconds}');

  @override
  Future<void> stop() async {
    calls.add('stop');
    _statuses.add(PlayerStatus.stopped);
  }

  void emitDuration(Duration d) => _durations.add(d);
  void emitPosition(Duration p) => _positions.add(p);
  void emitComplete() => _statuses.add(PlayerStatus.completed);

  @override
  Stream<Duration> get positions => _positions.stream;
  @override
  Stream<Duration> get durations => _durations.stream;
  @override
  Stream<PlayerStatus> get statuses => _statuses.stream;

  @override
  Future<void> dispose() async {
    await _positions.close();
    await _durations.close();
    await _statuses.close();
  }
}
