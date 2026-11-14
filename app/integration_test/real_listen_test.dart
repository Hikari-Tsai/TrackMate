// Listens to real files in the real macOS app through the system player (no Pro Tools needed):
// a 24-bit WAV, a stereo AIFF and a FLAC from STEMS_DIR each play, report their duration and
// advance; pause, seek and close work. See app/README.md for the command.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:stem_import/app_state.dart';
import 'package:stem_import/main.dart';
import 'package:stem_import/player.dart';

import 'support.dart';

const stemsDir = String.fromEnvironment('STEMS_DIR');

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('every stem plays in the bar', (tester) async {
    await tester.pumpWidget(const StemImportApp());
    base = binding.currentSystemFrameTimeStamp + const Duration(milliseconds: 16);
    sinceSwitch.start();
    binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmark;
    final state = tester.state<StemImportAppState>(find.byType(StemImportApp)).state;
    await waitFor(tester, () => state.engineState != EngineState.starting);
    expect(state.engineError, isNull);
    final adding = state.addFiles([stemsDir]);
    await waitFor(tester, () => !state.busy && state.tracks.isNotEmpty);
    await adding;
    await settle(tester);
    mark('analysed ${state.tracks.length} files');
    final a = state.audition;
    for (final row in state.tracks) {
      await tester.tap(find.byKey(ValueKey('listen-${row.originalName}')));
      await waitFor(tester, () => a.error != null || (a.duration != null && a.position.value > const Duration(milliseconds: 300)),
          seconds: 15);
      expect(a.error, isNull, reason: row.file);
      expect(a.track, row);
      expect(a.playing, isTrue);
      expect(a.duration!.inMilliseconds, closeTo(6000, 100), reason: row.file);
      mark('${row.originalName}: ${clock(a.position.value)} / ${clock(a.duration!)} playing');
    }
    // Pause holds the position, seek moves it, the end of the file turns the button back.
    await tester.tap(find.byKey(const ValueKey('player-toggle')));
    await waitFor(tester, () => !a.playing, seconds: 5);
    await settle(tester, ms: 300); // the tick already on its way
    final held = a.position.value;
    await settle(tester);
    expect(a.position.value, held);
    await a.seek(const Duration(seconds: 5));
    await tester.tap(find.byKey(const ValueKey('player-toggle')));
    await waitFor(tester, () => a.status == PlayerStatus.completed, seconds: 10);
    mark('played to the end: ${clock(a.position.value)}');
    expect(find.byKey(const ValueKey('player-bar')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('player-close')));
    await settle(tester);
    expect(a.track, isNull);
    expect(find.byKey(const ValueKey('player-bar')), findsNothing);
  });
}
