// Helpers for the integration tests that drive the real app.
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

final _clock = Stopwatch()..start();

void mark(String step) => debugPrint('[${(_clock.elapsedMilliseconds / 1000).toStringAsFixed(1)} s] $step');

/// Polls in real time and draws a frame each round. The app under test runs in the
/// background, where macOS sends it almost no vsync, so frames are driven directly
/// (frame policy `benchmark` + pumpBenchmark) instead of waiting for vsync.
/// Frame timestamps continue from the last vsync frame, so running animations never see time
/// go backwards.
Duration base = Duration.zero;
final sinceSwitch = Stopwatch();

Future<void> frame(WidgetTester tester) => tester.pumpBenchmark(base + sinceSwitch.elapsed);

Future<void> waitFor(WidgetTester tester, bool Function() done, {int seconds = 180}) async {
  final sw = Stopwatch()..start();
  while (sw.elapsed.inSeconds < seconds) {
    await frame(tester);
    if (done()) return;
    await Future<void>.delayed(const Duration(milliseconds: 50));
  }
  fail('timed out after $seconds s');
}

Future<void> settle(WidgetTester tester, {int ms = 500}) async {
  final sw = Stopwatch()..start();
  while (sw.elapsedMilliseconds < ms) {
    await frame(tester);
    await Future<void>.delayed(const Duration(milliseconds: 16));
  }
}
