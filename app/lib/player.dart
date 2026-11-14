/// Listening to a stem before it is imported: the player behind the Listen buttons and the
/// bar at the bottom of the list.
library;

import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';

import 'models.dart';

enum PlayerStatus { stopped, playing, paused, completed }

/// What the screen needs from an audio player. The app uses [AudioplayersPlayer]; the tests a
/// fake that records the calls.
abstract class StemPlayer {
  /// Loads [file] and starts playing it from the beginning; throws when the file cannot be played.
  Future<void> play(String file);
  Future<void> resume();
  Future<void> pause();
  Future<void> seek(Duration position);
  Future<void> stop();
  Stream<Duration> get positions;
  Stream<Duration> get durations;
  Stream<PlayerStatus> get statuses;
  Future<void> dispose();
}

/// The system's own decoder through the audioplayers package: AVFoundation on macOS, Media
/// Foundation on Windows, so every format the OS plays is heard as it is.
class AudioplayersPlayer implements StemPlayer {
  AudioplayersPlayer() : _player = AudioPlayer() {
    _player.setReleaseMode(ReleaseMode.stop);
  }

  final AudioPlayer _player;

  @override
  Future<void> play(String file) async {
    await _player.stop();
    await _player.play(DeviceFileSource(file));
  }

  @override
  Future<void> resume() => _player.resume();
  @override
  Future<void> pause() => _player.pause();
  @override
  Future<void> seek(Duration position) => _player.seek(position);
  @override
  Future<void> stop() => _player.stop();

  @override
  Stream<Duration> get positions => _player.onPositionChanged;
  @override
  Stream<Duration> get durations => _player.onDurationChanged;
  @override
  Stream<PlayerStatus> get statuses => _player.onPlayerStateChanged.map((s) => switch (s) {
        PlayerState.playing => PlayerStatus.playing,
        PlayerState.paused => PlayerStatus.paused,
        PlayerState.completed => PlayerStatus.completed,
        PlayerState.stopped || PlayerState.disposed => PlayerStatus.stopped,
      });

  @override
  Future<void> dispose() => _player.dispose();
}

/// Player that plays nothing: the app without a platform player (tests that do not listen).
class SilentPlayer implements StemPlayer {
  @override
  Future<void> play(String file) async {}
  @override
  Future<void> resume() async {}
  @override
  Future<void> pause() async {}
  @override
  Future<void> seek(Duration position) async {}
  @override
  Future<void> stop() async {}
  @override
  Stream<Duration> get positions => const Stream.empty();
  @override
  Stream<Duration> get durations => const Stream.empty();
  @override
  Stream<PlayerStatus> get statuses => const Stream.empty();
  @override
  Future<void> dispose() async {}
}

/// The track being listened to, its playback state and the player bar's controls. Notifies on
/// track, status, duration and error changes; the position has its own notifier so that the
/// rows do not rebuild five times a second.
class Audition extends ChangeNotifier {
  Audition(this.player) {
    _subs = [
      player.positions.listen((p) => position.value = p),
      player.durations.listen((d) {
        duration = d;
        notifyListeners();
      }),
      player.statuses.listen((s) {
        if (track == null) return;
        status = s;
        if (s == PlayerStatus.completed && duration != null) position.value = duration!;
        notifyListeners();
      }),
    ];
  }

  final StemPlayer player;
  late final List<StreamSubscription<Object?>> _subs;
  TrackRow? track;
  PlayerStatus status = PlayerStatus.stopped;
  Duration? duration;
  final position = ValueNotifier(Duration.zero);
  /// Why the file could not be played (shown in the bar instead of the slider).
  String? error;

  bool get playing => status == PlayerStatus.playing;
  bool isPlaying(TrackRow row) => track == row && playing;

  /// The row's Listen button: starts the track, or pauses and resumes it when it is the one
  /// in the bar already.
  Future<void> listen(TrackRow row) async {
    if (track == row && error == null) return toggle();
    track = row;
    error = null;
    duration = null;
    position.value = Duration.zero;
    status = PlayerStatus.playing;
    notifyListeners();
    try {
      await player.play(row.file);
    } catch (e) {
      if (track != row) return;
      error = _describe(e);
      status = PlayerStatus.stopped;
      notifyListeners();
    }
  }

  Future<void> toggle() async {
    if (track == null || error != null) return;
    if (playing) {
      status = PlayerStatus.paused;
      notifyListeners();
      await player.pause();
    } else if (status == PlayerStatus.completed) {
      position.value = Duration.zero;
      status = PlayerStatus.playing;
      notifyListeners();
      await player.seek(Duration.zero);
      await player.resume();
    } else {
      status = PlayerStatus.playing;
      notifyListeners();
      await player.resume();
    }
  }

  Future<void> seek(Duration to) async {
    if (track == null || error != null) return;
    position.value = to;
    if (status == PlayerStatus.completed) {
      status = PlayerStatus.paused;
      notifyListeners();
    }
    await player.seek(to);
  }

  /// Closes the bar and stops the sound.
  Future<void> close() async {
    if (track == null) return;
    track = null;
    status = PlayerStatus.stopped;
    error = null;
    duration = null;
    position.value = Duration.zero;
    notifyListeners();
    await player.stop();
  }

  /// Called when a row leaves the list.
  Future<void> forget(TrackRow row) => track == row ? close() : Future.value();

  static String _describe(Object e) {
    final text = '$e'.replaceFirst(RegExp(r'^\w*Exception: '), '');
    return 'Cannot play this file ($text)';
  }

  @override
  void dispose() {
    for (final s in _subs) {
      s.cancel();
    }
    position.dispose();
    player.dispose();
    super.dispose();
  }
}

/// "3:07" or "1:02:07" for the player bar.
String clock(Duration d) {
  final s = d.inSeconds;
  final m = (s ~/ 60) % 60;
  final sec = (s % 60).toString().padLeft(2, '0');
  return s >= 3600 ? '${s ~/ 3600}:${m.toString().padLeft(2, '0')}:$sec' : '$m:$sec';
}
