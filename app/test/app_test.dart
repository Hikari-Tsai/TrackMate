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

Future<(AppState, FakeEngine)> pumpApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1320, 820);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final fake = FakeEngine();
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
}
