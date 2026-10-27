// Drives the real macOS app against the real engine and Pro Tools. Needs an open *test*
// session in Pro Tools; the run adds folders and tracks to it. See app/README.md for the command.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:stem_import/app_state.dart';
import 'package:stem_import/main.dart';

const stemsDir = String.fromEnvironment('STEMS_DIR');

final _clock = Stopwatch()..start();

void mark(String step) => debugPrint('[${(_clock.elapsedMilliseconds / 1000).toStringAsFixed(1)} s] $step');

/// Polls in real time and draws a frame each round. The app under test runs in the
/// background, where macOS sends it almost no vsync, so frames are driven directly
/// (frame policy `benchmark` + pumpBenchmark) instead of waiting for vsync.
/// Frame timestamps continue from the last vsync frame, so running animations never see time
/// go backwards.
Duration _base = Duration.zero;
final _sinceSwitch = Stopwatch();

Future<void> frame(WidgetTester tester) => tester.pumpBenchmark(_base + _sinceSwitch.elapsed);

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

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('drop stems, correct one, preview and apply to Pro Tools', (tester) async {
    await tester.pumpWidget(const StemImportApp());
    _base = binding.currentSystemFrameTimeStamp + const Duration(milliseconds: 16);
    _sinceSwitch.start();
    binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmark;
    final app = tester.state<StemImportAppState>(find.byType(StemImportApp));
    final state = app.state;
    mark('app started');
    await waitFor(tester, () => state.engineState != EngineState.starting);
    mark('engine ready');
    expect(state.engineError, isNull);
    expect(state.layers, {'A': true, 'B': true, 'C': true, 'D': true});
    await waitFor(tester, () => state.session != null || state.sessionError != null);
    expect(state.session?['session'], isNotNull, reason: 'open a test session in Pro Tools');

    // Same entry point the native drop uses (NativeBridge.onFilesDropped -> addFiles).
    mark('session read');
    final adding = state.addFiles([stemsDir]);
    await waitFor(tester, () => !state.busy && state.tracks.isNotEmpty);
    await adding;
    await settle(tester);
    mark('analysed');
    expect(state.tracks, hasLength(10));
    final audio3 = state.tracks.firstWhere((t) => t.originalName == 'MySong_Audio 3');
    expect((audio3.category, audio3.stage), ('strings', 'D'));

    // Correct the synth pad through the Top-5 menu: pick the second candidate.
    final pad = state.tracks.firstWhere((t) => t.originalName == 'MySong_Synth Pad');
    final second = pad.candidates[1];
    await tester.ensureVisible(find.byKey(const ValueKey('candidates-MySong_Synth Pad')));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('candidates-MySong_Synth Pad')));
    final item = find.byKey(ValueKey('candidate-${second.instrument}'));
    await waitFor(tester, () => item.evaluate().isNotEmpty, seconds: 10);
    await settle(tester); // menu entrance animation
    await tester.tap(item);
    await waitFor(tester, () => pad.instrument == second.instrument, seconds: 10);

    mark('corrected via menu');
    await tester.tap(find.byKey(const ValueKey('apply-button')));
    await waitFor(tester, () => find.byKey(const ValueKey('confirm-apply')).evaluate().isNotEmpty, seconds: 30);
    await settle(tester);
    mark('preview shown');
    await tester.tap(find.byKey(const ValueKey('confirm-apply')));
    await waitFor(tester, () => find.byKey(const ValueKey('close-result')).evaluate().isNotEmpty, seconds: 120);
    await settle(tester);
    mark('applied');
    expect(find.textContaining('imported and verified'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('close-result')));
    await settle(tester);
    for (final t in state.tracks) {
      expect(t.applyResult?['name_ok'], isTrue, reason: t.originalName);
      expect(t.applyResult?['folder_ok'], isTrue, reason: t.originalName);
      expect(t.applyResult?['color_ok'], isTrue, reason: t.originalName);
    }
    final padResult = pad.applyResult!;
    debugPrint('synth pad -> ${padResult['pt_name']} in ${padResult['folder']}');
    debugPrint('apply message: ${state.message}');
  });
}
