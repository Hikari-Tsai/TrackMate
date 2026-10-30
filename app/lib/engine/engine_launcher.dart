import 'dart:async';
import 'dart:convert';
import 'dart:ffi' show Abi;
import 'dart:io';

import 'engine_api.dart';

/// How to reach the engine, from --dart-define values:
///   ENGINE_ATTACH  path to an engine.json of an engine that is already running
///   ENGINE_CMD     engine executable to start; default: the engine bundled with the app
///                  (TrackMate.app/Contents/Resources/engine/arm64 or engine/x86_64, or
///                  engine\ next to TrackMate.exe),
///                  else `stem-engine` on PATH
///   ENGINE_ARGS    extra arguments, space separated (e.g. --port 8765)
///   ENGINE_HOME    STEM_ENGINE_HOME for the started engine
class EngineConfig {
  const EngineConfig({this.attach = '', this.command = '', this.args = '', this.home = ''});

  factory EngineConfig.fromEnvironment() => const EngineConfig(
        attach: String.fromEnvironment('ENGINE_ATTACH'),
        command: String.fromEnvironment('ENGINE_CMD'),
        args: String.fromEnvironment('ENGINE_ARGS'),
        home: String.fromEnvironment('ENGINE_HOME'),
      );

  final String attach;
  final String command;
  final String args;
  final String home;
}

/// The engine shipped inside the app, or null in a development build.
String? bundledEngine() {
  final exe = File(Platform.resolvedExecutable).parent; // .../Contents/MacOS or the .exe folder
  // The universal macOS app carries one engine per architecture (engine/arm64, engine/x86_64).
  final macArch = Abi.current() == Abi.macosX64 ? 'x86_64' : 'arm64';
  final candidates = Platform.isMacOS
      ? [
          '${exe.parent.path}/Resources/engine/$macArch/stem-engine',
          '${exe.parent.path}/Resources/engine/stem-engine',
        ]
      : Platform.isWindows
          ? ['${exe.path}\\engine\\stem-engine.exe']
          : ['${exe.path}/engine/stem-engine'];
  for (final c in candidates) {
    if (File(c).existsSync()) return c;
  }
  return null;
}

/// Same rule as the engine's default_home(): where engine.json is written.
String defaultEngineHome() {
  final env = Platform.environment;
  if (Platform.isWindows) {
    final appData = env['APPDATA'] ?? '${env['USERPROFILE']}\\AppData\\Roaming';
    return '$appData\\TrackMate';
  }
  final home = env['HOME'] ?? '';
  if (Platform.isMacOS) return '$home/Library/Application Support/TrackMate';
  return '${env['XDG_DATA_HOME'] ?? '$home/.local/share'}/TrackMate';
}

class EngineConnection {
  EngineConnection(this.api, this.process);
  final HttpEngineApi api;
  final Process? process; // null when attached to an engine started elsewhere

  void stop() => process?.kill();
}

class EngineLauncher {
  static Future<EngineConnection> connect(EngineConfig cfg) async {
    if (cfg.attach.isNotEmpty) {
      final info = jsonDecode(await File(cfg.attach).readAsString()) as Map<String, dynamic>;
      final api = _api(info);
      if (!await api.health()) throw StateError('engine in ${cfg.attach} does not answer');
      return EngineConnection(api, null);
    }
    final command = cfg.command.isNotEmpty ? cfg.command : (bundledEngine() ?? 'stem-engine');
    final home = cfg.home.isNotEmpty ? cfg.home : defaultEngineHome();
    final infoFile = File('$home${Platform.pathSeparator}engine.json');
    final started = DateTime.now();
    final env = {if (cfg.home.isNotEmpty) 'STEM_ENGINE_HOME': cfg.home};
    // The app decides which models are downloaded (the models dialog), so the engine must not
    // start every download by itself.
    final args = {'--no-download', ...cfg.args.split(' ').where((a) => a.isNotEmpty)}.toList();
    final process = await Process.start(command, args, environment: env);
    // The engine announces {"port", "token", "pid"} on its first stdout line and in
    // engine.json; a packaged Windows engine has no stdout, so both are watched. Both pipes
    // are drained so the engine never blocks on a full pipe.
    final first = Completer<String>();
    process.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (!first.isCompleted && line.trimLeft().startsWith('{')) first.complete(line);
    });
    final errors = StringBuffer();
    process.stderr.transform(utf8.decoder).listen(errors.write);
    unawaited(process.exitCode.then((code) {
      if (!first.isCompleted) first.completeError(StateError('engine exited ($code): $errors'));
    }));
    final poll = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (first.isCompleted || !infoFile.existsSync()) return;
      if (infoFile.lastModifiedSync().isBefore(started.subtract(const Duration(seconds: 2)))) return;
      final text = infoFile.readAsStringSync();
      if (text.trim().isNotEmpty) first.complete(text);
    });
    final String line;
    try {
      line = await first.future.timeout(const Duration(seconds: 90));
    } finally {
      poll.cancel();
    }
    final api = _api(jsonDecode(line) as Map<String, dynamic>);
    for (var i = 0; i < 100 && !await api.health(); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
    }
    return EngineConnection(api, process);
  }

  static HttpEngineApi _api(Map<String, dynamic> info) =>
      HttpEngineApi(Uri.parse('http://127.0.0.1:${info['port']}'), info['token'] as String);
}
