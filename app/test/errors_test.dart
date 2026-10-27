// What the user sees when something is missing or breaks: Pro Tools closed, no session,
// Pro Tools busy or quitting during the import, files moved, the engine stopped.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:stem_import/alerts.dart';
import 'package:stem_import/app_state.dart';
import 'package:stem_import/engine/engine_api.dart';
import 'package:stem_import/ui/home_page.dart';
import 'package:stem_import/ui/theme.dart';

import 'fake_engine.dart';

EngineException err(String code, {int status = 503, List<String> files = const []}) =>
    EngineException(status, 'engine says $code', code: code, files: files);

Future<(AppState, FakeEngine)> start(WidgetTester tester, {bool addFiles = true}) async {
  tester.view.physicalSize = const Size(1320, 820);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final fake = FakeEngine();
  final state = AppState();
  await tester.runAsync(() => state.attach(fake));
  await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: HomePage(state: state)));
  if (addFiles) await tester.runAsync(() => state.addFiles(fake.files));
  await tester.pumpAndSettle();
  return (state, fake);
}

Future<void> settle(WidgetTester tester) async {
  await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
  await tester.pumpAndSettle();
}

/// Goes past the tempo step of Preview & apply when it is shown.
Future<void> passTempo(WidgetTester tester) async {
  final next = find.byKey(const ValueKey('tempo-continue'));
  if (next.evaluate().isEmpty) return;
  await tester.tap(next);
  await settle(tester);
}

Future<void> pressApply(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('apply-button')));
  await settle(tester);
  await passTempo(tester);
}

void main() {
  test('every engine error code has its own message', () {
    for (final (code, title, action) in [
      ('pro_tools_not_running', 'Pro Tools is not running', AlertAction.tryAgain),
      ('no_session', 'No session is open in Pro Tools', AlertAction.tryAgain),
      ('pro_tools_not_responding', 'Pro Tools is not responding', AlertAction.tryAgain),
      ('pro_tools_lost', 'Pro Tools stopped during the import', AlertAction.none),
      ('missing_files', 'Files not found', AlertAction.none),
      ('engine_unreachable', 'The TrackMate engine stopped', AlertAction.restartEngine),
    ]) {
      final a = AppAlert.fromError(err(code));
      expect((a.title, a.action, a.code), (title, action, code));
    }
    expect(AppAlert.fromError(EngineException(500, 'boom'), doing: 'apply to Pro Tools').title, 'Could not apply to Pro Tools');
  });

  testWidgets('apply stays clickable without Pro Tools and explains why it cannot go on', (tester) async {
    final (state, fake) = await start(tester);
    fake.sessionQueue.add(err('pro_tools_not_running'));
    await pressApply(tester);
    expect(find.byKey(const ValueKey('alert-pro_tools_not_running')), findsOneWidget);
    expect(find.text('Open Pro Tools and a session, then try again.'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('alert-close')));
    await settle(tester);
    expect(fake.applied, isEmpty); // nothing was sent
  });

  testWidgets('Try again goes on once Pro Tools is open', (tester) async {
    final (state, fake) = await start(tester);
    fake.sessionQueue.addAll([err('pro_tools_not_running'), 'no_session']);
    await pressApply(tester);
    await tester.tap(find.byKey(const ValueKey('alert-action'))); // user opened Pro Tools
    await settle(tester);
    expect(find.byKey(const ValueKey('alert-no_session')), findsOneWidget); // ... but no session yet
    await tester.tap(find.byKey(const ValueKey('alert-action'))); // user opened a session
    await settle(tester);
    await passTempo(tester);
    expect(find.byKey(const ValueKey('confirm-apply')), findsOneWidget); // preview shown
    expect(fake.sessionCalls, greaterThanOrEqualTo(3));
  });

  testWidgets('Pro Tools busy during the preview', (tester) async {
    final (_, fake) = await start(tester);
    fake.previewError = err('pro_tools_not_responding', status: 504);
    await pressApply(tester);
    expect(find.byKey(const ValueKey('alert-pro_tools_not_responding')), findsOneWidget);
    fake.previewError = null;
    await tester.tap(find.byKey(const ValueKey('alert-action')));
    await settle(tester);
    await passTempo(tester);
    expect(find.byKey(const ValueKey('confirm-apply')), findsOneWidget);
  });

  testWidgets('Pro Tools quits during the import', (tester) async {
    final (state, fake) = await start(tester);
    fake.applyError = err('pro_tools_lost');
    await pressApply(tester);
    await tester.tap(find.byKey(const ValueKey('confirm-apply')));
    await settle(tester);
    expect(find.byKey(const ValueKey('alert-pro_tools_lost')), findsOneWidget);
    expect(find.textContaining('may already be in the session'), findsOneWidget);
    expect(find.text('engine says pro_tools_lost'), findsOneWidget); // engine's detail is shown
    expect(state.busy, isFalse);
  });

  testWidgets('files moved before the import are listed', (tester) async {
    final (_, fake) = await start(tester);
    fake.applyError = err('missing_files', status: 404, files: ['/stems/Kick In.wav', '/stems/OH.wav']);
    await pressApply(tester);
    await tester.tap(find.byKey(const ValueKey('confirm-apply')));
    await settle(tester);
    expect(find.byKey(const ValueKey('alert-missing_files')), findsOneWidget);
    expect(find.text('/stems/Kick In.wav\n/stems/OH.wav'), findsOneWidget);
  });

  testWidgets('dropping something without audio files', (tester) async {
    final (state, _) = await start(tester, addFiles: false);
    await tester.runAsync(() => state.addFiles(['/tmp/notes.txt', '/tmp/cover.jpg']));
    await settle(tester);
    expect(find.byKey(const ValueKey('alert-no_audio_files')), findsOneWidget);
    expect(state.tracks, isEmpty);
  });

  testWidgets('files that vanished during recognition are dropped, the rest is analysed', (tester) async {
    final (state, fake) = await start(tester, addFiles: false);
    final gone = fake.files.first;
    fake.analyzeError = err('missing_files', status: 404, files: [gone]);
    await tester.runAsync(() => state.addFiles(fake.files));
    await settle(tester);
    expect(find.byKey(const ValueKey('alert-missing_files')), findsOneWidget);
    expect(state.tracks.map((t) => t.file), isNot(contains(gone)));
    expect(state.tracks, hasLength(fake.files.length - 1));
    expect(state.tracks.every((t) => t.stage != 'none' || t.originalName.contains('Audio')), isTrue);
  });

  testWidgets('engine stopped: Restart engine restarts it', (tester) async {
    final (state, fake) = await start(tester, addFiles: false);
    var restarts = 0;
    state.restartEngine = () async => restarts++;
    fake.analyzeError = err('engine_unreachable', status: 0);
    await tester.runAsync(() => state.addFiles(fake.files));
    await settle(tester);
    expect(find.byKey(const ValueKey('alert-engine_unreachable')), findsOneWidget);
    expect(find.text('Restart engine'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('alert-action')));
    await settle(tester);
    expect(restarts, 1);
  });

  testWidgets('engine that failed to start offers a restart button', (tester) async {
    final (state, _) = await start(tester, addFiles: false);
    var restarts = 0;
    state.restartEngine = () async => restarts++;
    state.fail(StateError('engine exited (1): ModuleNotFoundError'));
    await tester.pumpAndSettle();
    expect(find.text('The TrackMate engine could not start'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('restart-engine')));
    expect(restarts, 1);
  });
}
