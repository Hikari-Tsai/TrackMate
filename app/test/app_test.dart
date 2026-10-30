import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:stem_import/app_state.dart';
import 'package:stem_import/engine/engine_api.dart';
import 'package:stem_import/models.dart';
import 'package:stem_import/native_bridge.dart';
import 'package:stem_import/ui/home_page.dart';
import 'package:stem_import/ui/theme.dart';

import 'fake_engine.dart';

Future<(AppState, FakeEngine)> pumpApp(WidgetTester tester, {FakeEngine? engine}) async {
  tester.view.physicalSize = const Size(1320, 820);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final fake = engine ?? FakeEngine();
  final state = AppState();
  await tester.runAsync(() => state.attach(fake));
  await tester.pumpWidget(MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: buildTheme(),
    home: HomePage(state: state),
  ));
  await tester.runAsync(() => state.addFiles(fake.files));
  await tester.pumpAndSettle();
  return (state, fake);
}

TrackRow row(AppState s, String name) => s.tracks.firstWhere((t) => t.originalName == name);

/// Rows lower in the list may be scrolled out of the test window.
Future<void> tapVisible(WidgetTester tester, Key key) async {
  await tester.ensureVisible(find.byKey(key));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(key));
}

Future<void> loadRealFonts(WidgetTester tester) async {
    // Load the app's real fonts (Geist, Geist Mono, Lucide icons) so the golden image is
    // readable; plain `flutter test` renders every glyph as a box.
    await tester.runAsync(() async {
      Future<void> load(String family, List<String> assets) async {
        final loader = FontLoader(family);
        for (final a in assets) {
          loader.addFont(rootBundle.load(a));
        }
        await loader.load();
      }

      await load('Geist', ['assets/fonts/Geist-Regular.ttf', 'assets/fonts/Geist-Medium.ttf', 'assets/fonts/Geist-SemiBold.ttf']);
      await load('GeistMono', ['assets/fonts/GeistMono-Regular.ttf', 'assets/fonts/GeistMono-Medium.ttf']);
      await load('packages/lucide_icons_flutter/Lucide', ['packages/lucide_icons_flutter/assets/lucide.ttf']);
      // CJK file names in the list fall back to a system font.
      final cjk = FontLoader('Arial Unicode MS')
        ..addFont(File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').readAsBytes().then((b) => b.buffer.asByteData()));
      await cjk.load();
    });
}

void main() {
  testWidgets('dropped files are analysed, text pass then audio pass', (tester) async {
    final (state, fake) = await pumpApp(tester);
    expect(state.tracks, hasLength(10));
    expect(fake.analyzed, ['none', 'auto']); // MySong_Audio 3 was settled only by audio (low)
    expect(find.text('MySong_Kick In'), findsOneWidget);
    expect(row(state, 'MySong_鋼琴').mono, isTrue); // fake stereo -> convert
    expect(row(state, 'MySong_OH').mono, isFalse);
    expect(row(state, 'MySong_Audio 3').needsReview, isTrue);
    expect(find.text('1 to review'), findsOneWidget);
  });

  test('duplicate names get a running number', () {
    expect(numberDuplicates(['Lead Vocal', 'Kick', 'Lead Vocal', 'Lead Vocal 1']),
        ['Lead Vocal 2', 'Kick', 'Lead Vocal 3', 'Lead Vocal 1']); // "Lead Vocal 1" is taken
    expect(numberDuplicates(['Tom 2', 'Tom 2']), ['Tom 2-1', 'Tom 2-2']);
    expect(numberDuplicates(['A', 'B']), ['A', 'B']);
  });

  testWidgets('Pro Tools suffixes: removed by default, kept with the switch, duplicates numbered', (tester) async {
    tester.view.physicalSize = const Size(1320, 820);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final fake = FakeEngine(analysis: 'analyze_pt.json');
    final state = AppState();
    await tester.runAsync(() => state.attach(fake));
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: HomePage(state: state)));
    await tester.runAsync(() => state.addFiles(fake.files));
    await tester.pumpAndSettle();
    List<String> names() => [for (final t in state.tracks) state.finalName(t)];
    expect(names(), ['Lead Vocal 2-1', 'Lead Vocal 2-2', 'Piano', 'Weird Thing', 'Guitar DI']);
    expect(tester.widget<TextField>(find.byKey(const ValueKey('name-LV2-CVox_04-02'))).controller!.text, 'Lead Vocal 2-2');

    state.rename(row(state, 'Weird Thing_03-01'), 'Room Tone'); // typed names are left alone
    await tester.tap(find.byKey(const ValueKey('keep-unknown')));
    await tester.pumpAndSettle();
    expect(state.keepUnknown, isTrue);
    expect(names(), ['Lead Vocal 2 CVox_04-01', 'Lead Vocal 2 CVox_04-02', 'Piano bip 02-01', 'Room Tone', 'Guitar DI AudSt_01']);

    state.setKeepUnknown(false);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('apply-button')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('tempo-continue')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('confirm-apply')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect([for (final t in fake.applied.last.$1) t['name']], ['Lead Vocal 2-1', 'Lead Vocal 2-2', 'Piano', 'Room Tone', 'Guitar DI']);
  });

  test('scores are shown as whole percentages', () {
    expect([percent(1.0), percent(0.3124), percent(0.865), percent(-0.2), percent(1.4)],
        ['100%', '31%', '87%', '0%', '100%']);
  });

  testWidgets('confidence column and menu show percentages', (tester) async {
    final (state, _) = await pumpApp(tester);
    final strings = row(state, 'MySong_Audio 3');
    expect(find.byKey(const ValueKey('score-MySong_Audio 3')), findsOneWidget);
    expect(tester.widget<Text>(find.byKey(const ValueKey('score-MySong_Audio 3'))).data, percent(strings.score!));
    expect(tester.widget<Text>(find.byKey(const ValueKey('score-MySong_Kick In'))).data, '100%'); // dictionary
    await tapVisible(tester, const ValueKey('candidates-MySong_Audio 3'));
    await tester.pumpAndSettle();
    for (final c in strings.candidates) {
      expect(find.descendant(of: find.byKey(ValueKey('candidate-${c.instrument}')), matching: find.text(percent(c.score))),
          findsOneWidget);
    }
  });

  testWidgets('choosing another Top-5 candidate renames, recolours and teaches the engine', (tester) async {
    final (state, fake) = await pumpApp(tester);
    final r = row(state, 'MySong_Audio 3');
    final other = r.candidates.firstWhere((c) => c.category != r.category);
    await tapVisible(tester, const ValueKey('candidates-MySong_Audio 3'));
    await tester.pumpAndSettle();
    expect(find.byKey(ValueKey('candidate-${other.instrument}')), findsOneWidget);
    await tester.tap(find.byKey(ValueKey('candidate-${other.instrument}')));
    await tester.pumpAndSettle();
    expect(r.instrument, other.instrument);
    expect(r.name, other.label);
    expect(r.category, other.category);
    expect(r.colorIndex, state.catalog!.category(other.category).colorIndex);
    expect(r.needsReview, isFalse);
    expect(fake.feedbacks, isEmpty); // "Audio 3" is a DAW default name: nothing to learn

    final pad = row(state, 'MySong_Synth Pad');
    await tapVisible(tester, const ValueKey('candidates-MySong_Synth Pad'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ValueKey('candidate-${pad.candidates[1].instrument}')));
    await tester.pumpAndSettle();
    expect(fake.feedbacks, [('synth pad', pad.candidates[1].instrument)]); // song title stripped
  });

  testWidgets('search all instruments and keep original name', (tester) async {
    final (state, _) = await pumpApp(tester);
    await tapVisible(tester, const ValueKey('candidates-MySong_Bass DI'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-search')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('instrument-search-field')), 'upright');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Upright Bass'));
    await tester.pumpAndSettle();
    expect(row(state, 'MySong_Bass DI').name, 'Upright Bass'); // 'bass di' matched as one phrase: no modifiers left

    await tapVisible(tester, const ValueKey('candidates-MySong_OH'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-keep')));
    await tester.pumpAndSettle();
    expect(row(state, 'MySong_OH').name, 'MySong_OH');
  });

  testWidgets('type a name from the dropdown', (tester) async {
    final (state, fake) = await pumpApp(tester);
    await tapVisible(tester, const ValueKey('candidates-MySong_Kick In'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-type')));
    await tester.pumpAndSettle();
    expect(find.text('Type a track name'), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('name-entry-field')), 'Kick Inside Mic');
    await tester.tap(find.byKey(const ValueKey('name-entry-ok')));
    await tester.pumpAndSettle();
    final r = row(state, 'MySong_Kick In');
    expect((r.name, r.edited, r.instrument), ('Kick Inside Mic', true, 'kick_in')); // instrument unchanged
    expect(tester.widget<TextField>(find.byKey(const ValueKey('name-MySong_Kick In'))).controller!.text, 'Kick Inside Mic');
    expect(fake.feedbacks, isEmpty); // a free-typed name is not an instrument choice

    // Empty input or Cancel leaves the name as it was.
    await tapVisible(tester, const ValueKey('candidates-MySong_Kick In'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('menu-type')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('name-entry-field')), '   ');
    await tester.tap(find.byKey(const ValueKey('name-entry-ok')));
    await tester.pumpAndSettle();
    expect(r.name, 'Kick Inside Mic');
  });

  testWidgets('category menu opens below the button and changes the category', (tester) async {
    final (state, _) = await pumpApp(tester);
    final r = row(state, 'MySong_Kick In');
    await tapVisible(tester, const ValueKey('category-MySong_Kick In'));
    await tester.pumpAndSettle();
    final button = tester.getRect(find.byKey(const ValueKey('category-MySong_Kick In')));
    final first = tester.getRect(find.byKey(const ValueKey('category-item-drums')));
    expect(first.top, greaterThanOrEqualTo(button.bottom)); // starts below the button
    await tester.tap(find.byKey(const ValueKey('category-item-percussion')));
    await tester.pumpAndSettle();
    expect((r.category, r.colorIndex), ('percussion', state.catalog!.category('percussion').colorIndex));
  });

  testWidgets('category change follows the default colour until a colour is picked', (tester) async {
    final (state, _) = await pumpApp(tester);
    final r = row(state, 'MySong_Synth Pad');
    state.setCategory(r, 'keys');
    expect(r.colorIndex, state.catalog!.category('keys').colorIndex);
    await tester.pumpAndSettle();
    await tapVisible(tester, const ValueKey('color-MySong_Synth Pad'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('swatch-40')));
    await tester.pumpAndSettle();
    expect((r.colorIndex, r.colorOverridden), (40, true));
    state.setCategory(r, 'synths');
    expect(r.colorIndex, 40); // user's colour is kept
  });

  testWidgets('preview then apply sends the edited tracks', (tester) async {
    final (state, fake) = await pumpApp(tester);
    state.rename(row(state, 'MySong_Lead Vox'), 'Lead Vox Main');
    state.setMono(row(state, 'MySong_鋼琴'), false);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('apply-button')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('tempo-continue')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(find.textContaining('Apply to Pro Tools: Demo Session'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('confirm-apply')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(find.textContaining('10 tracks imported and verified'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('close-result')));
    await tester.pumpAndSettle();
    expect(fake.applied.map((a) => a.$2), [true, false]);
    final sent = fake.applied.last.$1;
    expect(sent.firstWhere((t) => (t['file'] as String).endsWith('MySong_Lead Vox.wav'))['name'], 'Lead Vox Main');
    expect(sent.firstWhere((t) => (t['file'] as String).endsWith('MySong_鋼琴.wav'))['mono'], isFalse);
    expect(state.tracks.every((t) => t.applyResult?['name_ok'] == true), isTrue);
    expect(find.byIcon(LucideIcons.circleCheck), findsWidgets);
  });

  testWidgets('the BPM is detected after adding stems and shown, not clickable, in the header', (tester) async {
    final (state, fake) = await pumpApp(tester);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    // Every track goes with its category; the engine picks the rhythm stems.
    expect(fake.tempoRequests, hasLength(1));
    expect(fake.tempoRequests.single.firstWhere((t) => (t['file'] as String).endsWith('Kick In.wav'))['category'], 'drums');
    expect(find.byKey(const ValueKey('tempo-bpm')), findsOneWidget);
    expect(find.text('85 BPM'), findsOneWidget);
    expect(find.text('Constant'), findsOneWidget);
    expect(find.byKey(const ValueKey('detect-bpm')), findsNothing); // no button: it is only a display
    await tester.tap(find.byKey(const ValueKey('tempo-chip')));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    // A changed list is detected again on its own.
    state.remove(row(state, 'MySong_BGVs'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(fake.tempoRequests, hasLength(2));
    expect(fake.tempoRequests.last, hasLength(9));
  });

  Future<void> next(WidgetTester tester, String key) async {
    await tester.tap(find.byKey(ValueKey(key)));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
  }

  testWidgets('Preview & apply asks for the tempo first and imports it after the tracks', (tester) async {
    final (state, fake) = await pumpApp(tester);
    await next(tester, 'apply-button');
    expect(find.text('Tempo for this import'), findsOneWidget);
    expect(find.byKey(const ValueKey('tempo-dialog-bpm')), findsOneWidget);
    expect(find.textContaining('Listened to 3 drum stems'), findsOneWidget);
    expect(find.byKey(const ValueKey('confirm-apply')), findsNothing); // the preview comes after the tempo
    await tester.tap(find.text('2× double time'));
    await tester.pumpAndSettle();
    expect(state.tempoBpm, 170);
    await tester.tap(find.text('Tempo map'));
    await tester.pumpAndSettle();
    expect(find.text('Continue with ≈ 170 BPM'), findsOneWidget);
    await next(tester, 'tempo-continue');
    expect(find.textContaining('Then sets the tempo: tempo map, ≈ 170 BPM'), findsOneWidget);
    await next(tester, 'confirm-apply');
    expect(find.textContaining('10 tracks imported and verified'), findsOneWidget);
    expect(find.textContaining('Tempo set: ≈ 170 BPM (checked in Pro Tools)'), findsOneWidget);
    expect(fake.calls, ['apply', 'tempo']); // tracks first, then the tempo
    final req = fake.tempoApplied.single;
    expect((req['mode'], req['bpm'], req['factor'], req['folder'], req['import_to_pro_tools']),
        ('variable', null, 2, '/stems', true));
    expect((req['beats'] as List).length, 324);
    await next(tester, 'close-result');
    expect(find.byIcon(LucideIcons.check), findsWidgets); // the header shows it was set
  });

  testWidgets('cancelled in Pro Tools: the result offers to import only the tempo again', (tester) async {
    final (state, fake) = await pumpApp(tester);
    fake.tempoAccepted = false;
    await next(tester, 'apply-button');
    await next(tester, 'tempo-continue');
    await next(tester, 'confirm-apply');
    expect(find.textContaining('The tempo was not changed'), findsOneWidget);
    expect(find.text('Done, with problems'), findsOneWidget);
    fake.tempoAccepted = true;
    await next(tester, 'retry-tempo');
    expect(find.textContaining('Tempo set: 85 BPM'), findsOneWidget);
    expect(find.byKey(const ValueKey('retry-tempo')), findsNothing);
    expect(fake.calls, ['apply', 'tempo', 'tempo']); // the tracks were not imported twice
    await next(tester, 'close-result');
  });

  testWidgets('keep the session tempo, or cancel at the tempo step', (tester) async {
    final (_, fake) = await pumpApp(tester);
    await next(tester, 'apply-button');
    await next(tester, 'tempo-cancel');
    expect(fake.applied, isEmpty); // nothing previewed or sent
    await next(tester, 'apply-button');
    await tester.tap(find.text('Keep session tempo'));
    await tester.pumpAndSettle();
    expect(find.text('Continue without tempo'), findsOneWidget);
    await next(tester, 'tempo-continue');
    expect(find.text('The session tempo is not changed.'), findsOneWidget);
    await next(tester, 'confirm-apply');
    expect(find.textContaining('The session tempo was not changed.'), findsOneWidget);
    expect(fake.calls, ['apply']);
    await next(tester, 'close-result');
  });

  testWidgets('no beat in the stems: the header says so and the import goes on without tempo', (tester) async {
    final fake = FakeEngine()..tempoError = EngineException(422, 'No steady beat found.', code: 'no_beats');
    final (state, _) = await pumpApp(tester, engine: fake);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(find.text('No BPM found'), findsOneWidget);
    expect(find.byType(AlertDialog), findsNothing); // no alert while the user reviews the names
    await next(tester, 'apply-button');
    expect(find.byKey(const ValueKey('tempo-error')), findsOneWidget);
    expect(find.textContaining('No steady beat was found in the stems'), findsOneWidget);
    fake.tempoError = null;
    await next(tester, 'tempo-retry'); // detect again, now with a beat
    expect(find.byKey(const ValueKey('tempo-dialog-bpm')), findsOneWidget);
    await tester.tap(find.text('Keep session tempo'));
    await tester.pumpAndSettle();
    await next(tester, 'tempo-continue');
    expect(find.byKey(const ValueKey('confirm-apply')), findsOneWidget);
    expect(state.tempoWillImport, isFalse);
  });

  testWidgets('screenshot of the tempo step', (tester) async {
    await loadRealFonts(tester);
    await pumpApp(tester);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('apply-button')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/tempo_dialog.png'));
  }, tags: ['golden'], skip: !File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').existsSync());

  testWidgets('screenshot', (tester) async {
    await loadRealFonts(tester);
    final (state, _) = await pumpApp(tester);
    await tapVisible(tester, const ValueKey('candidates-MySong_Audio 3'));
    await tester.pumpAndSettle();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/track_list.png'));
    expect(state.tracks, isNotEmpty);
  }, tags: ['golden'], skip: !File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').existsSync());

  testWidgets('screenshot of the category menu', (tester) async {
    await loadRealFonts(tester);
    await pumpApp(tester);
    await tapVisible(tester, const ValueKey('category-MySong_Kick In'));
    await tester.pumpAndSettle();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/category_menu.png'));
  }, tags: ['golden'], skip: !File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').existsSync());

  testWidgets('screenshot of the Pro Tools alert', (tester) async {
    await loadRealFonts(tester);
    final (_, fake) = await pumpApp(tester);
    fake.sessionQueue.add(EngineException(503, 'Pro Tools is not running.', code: 'pro_tools_not_running'));
    await tester.tap(find.byKey(const ValueKey('apply-button')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pumpAndSettle();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/alert_pro_tools.png'));
  }, tags: ['golden'], skip: !File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').existsSync());

  testWidgets('screenshot of the empty state', (tester) async {
    await loadRealFonts(tester);
    tester.view.physicalSize = const Size(1320, 820);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final state = AppState();
    await tester.runAsync(() => state.attach(FakeEngine()));
    await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: HomePage(state: state, bridge: NativeBridge(onFilesDropped: (_) {}, onDragHover: (_) {}))));
    await tester.pumpAndSettle();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/empty_state.png'));
  }, tags: ['golden'], skip: !File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').existsSync());

  // ------------------------------------------------------------- models window
  Future<(AppState, FakeEngine)> pumpHome(WidgetTester tester, FakeEngine fake) async {
    tester.view.physicalSize = const Size(1320, 820);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final state = AppState();
    await tester.runAsync(() => state.attach(fake));
    await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: HomePage(state: state)));
    await tester.pumpAndSettle();
    return (state, fake);
  }

  testWidgets('first start: the models window opens when a model is missing, with a ready mark per model', (tester) async {
    final fake = FakeEngine()..setModel('beat_this', 'missing')..setModel('peav_audio', 'missing');
    final (state, _) = await pumpHome(tester, fake);
    expect(find.byKey(const ValueKey('models-dialog')), findsOneWidget);
    expect(find.byKey(const ValueKey('models-ready-qwen3_embedding')), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
    expect(find.byKey(const ValueKey('models-missing-peav_audio')), findsOneWidget);
    expect(find.byKey(const ValueKey('models-missing-beat_this')), findsOneWidget);
    // Each row names its layer and size; the text gives the total.
    expect(find.text('AI name reading'), findsOneWidget);
    expect(find.text('1.13 GB'), findsOneWidget);
    expect(find.text('222 MB'), findsOneWidget);
    expect(find.text('82 MB'), findsOneWidget);
    expect(find.textContaining('1.43 GB in all'), findsOneWidget);
    // A ready model cannot be ticked; "Download selected" waits for a tick.
    expect(tester.widget<Checkbox>(find.byKey(const ValueKey('models-pick-qwen3_embedding'))).onChanged, isNull);
    expect(tester.widget<Checkbox>(find.byKey(const ValueKey('models-pick-beat_this'))).onChanged, isNotNull);
    expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('models-download-selected'))).enabled, isFalse);
    expect(tester.widget<FilledButton>(find.byKey(const ValueKey('models-download-all'))).enabled, isTrue);
    expect(find.text('2 models not downloaded'), findsOneWidget); // the header
    expect(fake.downloads, isEmpty); // nothing starts without the user
    // "Later" closes it, and it does not come back on its own.
    await tester.tap(find.byKey(const ValueKey('models-close')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-dialog')), findsNothing);
    state.setDragHover(true);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-dialog')), findsNothing);
    expect(state.layers['T'], isFalse);
  });

  testWidgets('tick one model and download it: its own progress bar, then the ready mark', (tester) async {
    final fake = FakeEngine()..setModel('beat_this', 'missing')..setModel('peav_audio', 'missing');
    final (state, _) = await pumpHome(tester, fake);
    await tester.tap(find.byKey(const ValueKey('models-pick-beat_this')));
    await tester.pumpAndSettle();
    expect(find.text('Download selected (1)'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('models-download-selected')));
    await tester.pumpAndSettle();
    expect(fake.downloads, [['beat_this']]);
    final bar = tester.widget<LinearProgressIndicator>(find.byKey(const ValueKey('models-progress-beat_this')));
    expect(bar.value, closeTo(0.36, 0.001));
    expect(find.text('30 MB of 82 MB · 36% · onnx/model.onnx'), findsOneWidget);
    expect(find.byKey(const ValueKey('models-missing-peav_audio')), findsOneWidget); // the other one is untouched
    expect(find.text('Downloading 1 model 36%'), findsOneWidget); // the header
    expect(tester.widget<TextButton>(find.byKey(const ValueKey('models-clear'))).enabled, isFalse); // not while downloading
    expect(tester.widget<Checkbox>(find.byKey(const ValueKey('models-pick-beat_this'))).onChanged, isNull);
    // The download finishes; the 2 s poll shows it.
    fake.setModel('beat_this', 'ready');
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-ready-beat_this')), findsOneWidget);
    expect(find.byKey(const ValueKey('models-progress-beat_this')), findsNothing);
    expect(state.tempoModelReady, isTrue);
    expect(find.text('1 model not downloaded'), findsOneWidget);
  });

  testWidgets('Download all starts every missing model and ends with every row ready', (tester) async {
    final fake = FakeEngine()..setModel('beat_this', 'missing')..setModel('peav_audio', 'missing');
    await pumpHome(tester, fake);
    await tester.tap(find.byKey(const ValueKey('models-download-all')));
    await tester.pumpAndSettle();
    expect(fake.downloads, [['peav_audio', 'beat_this']]);
    expect(find.byType(LinearProgressIndicator), findsNWidgets(2));
    expect(find.text('Downloading 2 models 36%'), findsOneWidget);
    fake.setModel('peav_audio', 'ready');
    fake.setModel('beat_this', 'ready');
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.text('Ready'), findsNWidgets(3));
    expect(find.text('All models ready'), findsOneWidget);
    expect(find.text('Done'), findsOneWidget);
    expect(find.text('Recognition ready'), findsOneWidget);
  });

  testWidgets('a failed download shows its error in the row, with a retry', (tester) async {
    final fake = FakeEngine()..setModel('beat_this', 'error', error: 'URLError: <urlopen error timed out>');
    await pumpHome(tester, fake);
    expect(find.byKey(const ValueKey('models-dialog')), findsOneWidget);
    expect(find.text('URLError: <urlopen error timed out>'), findsOneWidget);
    expect(find.text('Model download failed'), findsOneWidget); // the header
    await tester.tap(find.byKey(const ValueKey('models-retry-beat_this')));
    await tester.pumpAndSettle();
    expect(fake.downloads, [['beat_this']]);
    expect(find.byKey(const ValueKey('models-progress-beat_this')), findsOneWidget);
    fake.setModel('beat_this', 'ready');
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-ready-beat_this')), findsOneWidget);
  });

  testWidgets('a download interrupted last time goes on by itself', (tester) async {
    final fake = FakeEngine()..setModel('beat_this', 'missing', onDisk: 30000000);
    final (state, _) = await pumpHome(tester, fake);
    expect(fake.downloads, [['beat_this']]);
    expect(find.byKey(const ValueKey('models-progress-beat_this')), findsOneWidget);
    fake.setModel('beat_this', 'ready');
    await tester.runAsync(state.refreshModels);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-ready-beat_this')), findsOneWidget);
  });

  testWidgets('Clear models: reachable from the header, asks first, says what it frees, empties the rows', (tester) async {
    final (state, fake) = await pumpHome(tester, FakeEngine());
    expect(find.byKey(const ValueKey('models-dialog')), findsNothing); // all ready: nothing to ask on start
    await tester.tap(find.byKey(const ValueKey('models-status')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-dialog')), findsOneWidget);
    expect(find.text('Ready'), findsNWidgets(3));
    expect(find.text('On disk: 1.43 GB'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('models-clear')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('models-clear-confirm')), findsOneWidget);
    expect(find.text('Delete 1.43 GB'), findsOneWidget);
    expect(find.text(fake.modelsDir), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('models-clear-cancel')));
    await tester.pumpAndSettle();
    expect(fake.clearCalls, 0);
    expect(find.text('Ready'), findsNWidgets(3));
    await tester.tap(find.byKey(const ValueKey('models-clear')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('models-clear-delete')));
    await tester.pumpAndSettle();
    expect(fake.clearCalls, 1);
    expect(find.byKey(const ValueKey('models-clear-confirm')), findsNothing);
    expect(find.text('Ready'), findsNothing);
    expect(find.text('Not downloaded'), findsNWidgets(3));
    expect(find.textContaining('Freed 1.43 GB'), findsOneWidget);
    expect(find.text('3 models not downloaded'), findsOneWidget);
    expect(state.layers, {'A': true, 'B': true, 'C': false, 'D': false, 'T': false});
    expect(tester.widget<TextButton>(find.byKey(const ValueKey('models-clear'))).enabled, isFalse);
    // Back to the initial state: tick and download again.
    await tester.tap(find.byKey(const ValueKey('models-pick-qwen3_embedding')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('models-download-selected')));
    await tester.pumpAndSettle();
    expect(fake.downloads, [['qwen3_embedding']]);
    fake.setModel('qwen3_embedding', 'ready');
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
  });

  testWidgets('clearing while the engine still downloads is refused (409) and explained', (tester) async {
    final (_, fake) = await pumpHome(tester, FakeEngine());
    fake.clearError = EngineException(409, 'Cannot delete the models now: a model is still downloading.',
        code: 'models_downloading');
    await tester.tap(find.byKey(const ValueKey('models-status')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('models-clear')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('models-clear-delete')));
    await tester.pumpAndSettle();
    expect(fake.clearCalls, 1);
    expect(find.byKey(const ValueKey('models-error')), findsOneWidget);
    expect(find.textContaining('A download is still running'), findsOneWidget);
    expect(find.text('Ready'), findsNWidgets(3)); // nothing was deleted
  });

  testWidgets('screenshot of the models window', (tester) async {
    await loadRealFonts(tester);
    final fake = FakeEngine()
      ..setModel('peav_audio', 'downloading', progress: 0.36, file: 'onnx/model_q8.onnx')
      ..setModel('beat_this', 'missing');
    final (state, _) = await pumpHome(tester, fake);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/models_dialog.png'));
    fake.setModel('peav_audio', 'ready');
    await tester.runAsync(state.refreshModels); // stops the 2 s poll
  }, tags: ['golden'], skip: !File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf').existsSync());
}
