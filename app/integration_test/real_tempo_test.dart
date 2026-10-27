// Drives the real macOS app, engine and Pro Tools through tempo detection and import. Needs an
// open *test* session in Pro Tools and someone (or a script) pressing OK in Pro Tools' "MIDI
// Import Options" dialog; the run changes the session tempo and adds the stems as tracks.
// STEMS_DIR: rhythm stems with a known constant tempo, TEMPO_BPM: that tempo.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:stem_import/app_state.dart';
import 'package:stem_import/main.dart';

import 'support.dart';

const stemsDir = String.fromEnvironment('STEMS_DIR');
const tempoBpm = int.fromEnvironment('TEMPO_BPM');

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('detect the BPM, import it, then apply tracks and tempo together', (tester) async {
    await tester.pumpWidget(const StemImportApp());
    base = binding.currentSystemFrameTimeStamp + const Duration(milliseconds: 16);
    sinceSwitch.start();
    binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmark;
    final state = tester.state<StemImportAppState>(find.byType(StemImportApp)).state;
    await waitFor(tester, () => state.engineState != EngineState.starting);
    expect(state.layers['T'], isTrue);
    await waitFor(tester, () => state.session != null || state.sessionError != null);
    expect(state.session?['session'], isNotNull, reason: 'open a test session in Pro Tools');
    mark('engine ready');

    final adding = state.addFiles([stemsDir]);
    await waitFor(tester, () => !state.busy && state.tracks.isNotEmpty);
    await adding;
    await settle(tester);
    mark('analysed: ${state.tracks.map((t) => '${t.name}=${t.category}').join(', ')}');

    await tester.tap(find.byKey(const ValueKey('detect-bpm')));
    await waitFor(tester, () => find.byKey(const ValueKey('tempo-dialog-bpm')).evaluate().isNotEmpty, seconds: 120);
    await settle(tester);
    final t = state.tempo!;
    mark('detected ${t.bpm} BPM (${t.suggestedMode}) from ${t.sources.length} ${t.sourceKind} stems in ${t.raw['seconds']} s');
    expect((t.bpmRounded, t.suggestedMode, t.sourceKind), (tempoBpm, 'constant', 'drums'));
    expect(find.descendant(of: find.byType(AlertDialog), matching: find.text('$tempoBpm BPM')), findsOneWidget);

    // From the dialog: constant tempo, verified in Pro Tools afterwards.
    await tester.tap(find.byKey(const ValueKey('tempo-import')));
    await waitFor(tester, () => find.byKey(const ValueKey('tempo-result')).evaluate().isNotEmpty, seconds: 300);
    await settle(tester);
    mark('dialog import: ${state.tempoResult}');
    expect(state.tempoResult!['applied'], isTrue);
    expect(find.textContaining('Pro Tools tempo is now $tempoBpm BPM'), findsOneWidget);

    // Tempo map, imported together with the tracks by Preview & apply.
    await tester.tap(find.text('Tempo map (variable)'));
    await settle(tester);
    await tester.tap(find.text('Close'));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('apply-button')));
    await waitFor(tester, () => find.byKey(const ValueKey('confirm-apply')).evaluate().isNotEmpty, seconds: 30);
    await settle(tester);
    expect(find.byKey(const ValueKey('apply-tempo-line')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('confirm-apply')));
    await waitFor(tester, () => find.byKey(const ValueKey('close-result')).evaluate().isNotEmpty, seconds: 300);
    await settle(tester);
    mark('applied with tempo: ${state.tempoResult}');
    expect(find.textContaining('imported and verified'), findsOneWidget);
    expect(find.textContaining('Tempo set: ≈ $tempoBpm BPM.'), findsOneWidget);
    expect((state.tempoResult!['mode'], state.tempoResult!['applied']), ('variable', true));
    await tester.tap(find.byKey(const ValueKey('close-result')));
    await settle(tester);
    expect(find.byKey(const ValueKey('tempo-bpm')), findsOneWidget);
  });
}
