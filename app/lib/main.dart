import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';

import 'app_state.dart';
import 'engine/engine_launcher.dart';
import 'native_bridge.dart';
import 'ui/home_page.dart';
import 'ui/theme.dart';

void main() {
  runApp(const StemImportApp());
}

class StemImportApp extends StatefulWidget {
  const StemImportApp({super.key, this.config});
  final EngineConfig? config;

  @override
  State<StemImportApp> createState() => StemImportAppState();
}

class StemImportAppState extends State<StemImportApp> {
  final state = AppState();
  late final NativeBridge bridge;
  EngineConnection? _engine;
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    bridge = NativeBridge(
      onFilesDropped: (paths) {
        if (state.engineState == EngineState.ready && !state.busy) state.addFiles(paths);
      },
      onDragHover: state.setDragHover,
    );
    _lifecycle = AppLifecycleListener(onExitRequested: () async {
      _engine?.stop();
      return AppExitResponse.exit;
    });
    state.restartEngine = _restart;
    unawaited(_connect());
  }

  /// Stops the engine process (if it still runs) and starts a new one; the track list stays.
  Future<void> _restart() async {
    _engine?.stop();
    _engine = null;
    state.engineRestarting();
    await _connect();
  }

  Future<void> _connect() async {
    try {
      _engine = await EngineLauncher.connect(widget.config ?? EngineConfig.fromEnvironment());
      await state.attach(_engine!.api);
    } catch (e) {
      state.fail(e);
    }
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    _engine?.stop();
    state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TrackMate',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: HomePage(state: state, bridge: bridge),
    );
  }
}
