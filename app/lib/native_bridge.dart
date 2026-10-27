import 'package:flutter/services.dart';

/// Talks to macos/Runner/MainFlutterWindow.swift: files dropped on the window, drag hover,
/// and the open panel.
class NativeBridge {
  NativeBridge({required this.onFilesDropped, required this.onDragHover}) {
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'filesDropped':
          onFilesDropped([for (final p in call.arguments as List) p as String]);
        case 'dragHover':
          onDragHover(call.arguments as bool);
      }
    });
  }

  static const _channel = MethodChannel('stem_import/native');
  final void Function(List<String> paths) onFilesDropped;
  final void Function(bool hovering) onDragHover;

  Future<List<String>> pickFiles() async {
    final res = await _channel.invokeMethod<List<Object?>>('pickFiles');
    return [for (final p in res ?? const []) p as String];
  }
}
