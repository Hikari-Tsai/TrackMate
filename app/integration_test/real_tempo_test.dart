// Drives the real macOS app, engine and Pro Tools through the tempo: detected on its own after
// the stems are added, chosen in the step before the import, imported after the tracks. Needs an
// open *test* session in Pro Tools and someone (or a script) pressing OK in Pro Tools' "MIDI
// Import Options" dialog; the run changes the session tempo and adds the stems twice.
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

  testWidgets('the BPM is detected on its own, chosen before the import and imported with the tracks', (tester) async {
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
    mark('analysed: ${state.tracks.map((t) => '${t.name}=${t.category}').join(', ')}');
    // No button: the tempo is detected on its own and shown in the header.
    await waitFor(tester, () => state.tempo != null || state.tempoError != null, seconds: 120);
    await settle(tester);
    final t = state.tempo!;
    mark('detected ${t.bpm} BPM (${t.suggestedMode}) from ${t.sources.length} ${t.sourceKind} stems in ${t.raw['seconds']} s');
    expect((t.bpmRounded, t.suggestedMode, t.sourceKind), (tempoBpm, 'constant', 'drums'));
    expect(find.byKey(const ValueKey('tempo-bpm')), findsOneWidget);
    expect(find.text('$tempoBpm BPM'), findsOneWidget);

    Future<void> applyWith(String mode) async {
      await tester.tap(find.byKey(const ValueKey('apply-button')));
      await waitFor(tester, () => find.byKey(const ValueKey('tempo-continue')).evaluate().isNotEmpty, seconds: 30);
      await settle(tester);
      await tester.tap(find.text(mode));
      await settle(tester);
      await tester.tap(find.byKey(const ValueKey('tempo-continue')));
      await waitFor(tester, () => find.byKey(const ValueKey('confirm-apply')).evaluate().isNotEmpty, seconds: 30);
      await settle(tester);
      expect(find.textContaining('Then sets the tempo'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('confirm-apply')));
      await waitFor(tester, () => find.byKey(const ValueKey('close-result')).evaluate().isNotEmpty, seconds: 300);
      await settle(tester);
      mark('applied with $mode: ${state.tempoResult}');
      expect(find.textContaining('imported and verified'), findsOneWidget);
      expect(find.textContaining('Tempo set: ${state.tempoLabel} (checked in Pro Tools)'), findsOneWidget);
      expect(state.tempoResult!['applied'], isTrue);
      await tester.tap(find.byKey(const ValueKey('close-result')));
      await settle(tester);
    }

    await applyWith('Constant tempo');
    expect(state.tempoResult!['mode'], 'constant');
    await applyWith('Tempo map');
    expect(state.tempoResult!['mode'], 'variable');
  });
}
