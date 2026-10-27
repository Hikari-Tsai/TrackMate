import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import 'dart:async';

import '../alerts.dart';
import '../app_state.dart';
import '../native_bridge.dart';
import 'alert_dialog.dart';
import 'apply_dialogs.dart';
import 'tempo_dialog.dart';
import 'theme.dart';
import 'track_table.dart';


/// Window (darkest) > rounded panel > header, track rows and footer with the actions.
/// Also shows the state's alerts (no audio files, engine stopped, …) as dialogs.
class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.state, this.bridge});
  final AppState state;
  final NativeBridge? bridge;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late final StreamSubscription<AppAlert> _alerts = widget.state.alerts.listen(_show);
  bool _showing = false;

  Future<void> _show(AppAlert alert) async {
    if (!mounted || _showing) return; // one dialog at a time
    _showing = true;
    final act = await showAlert(context, alert);
    _showing = false;
    if (act && alert.action == AlertAction.restartEngine) await widget.state.restartEngine?.call();
  }

  @override
  void initState() {
    super.initState();
    _alerts; // subscribe now
  }

  @override
  void dispose() {
    _alerts.cancel();
    super.dispose();
  }

  AppState get state => widget.state;
  NativeBridge? get bridge => widget.bridge;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: state,
      builder: (context, _) => Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(10),
          child: Stack(children: [
            Container(
              decoration: BoxDecoration(
                color: Palette.panel,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Palette.border),
              ),
              clipBehavior: Clip.antiAlias,
              child: Column(children: [
                _Header(state: state),
                const Divider(),
                _SessionBar(state: state),
                Expanded(child: _Body(state: state, bridge: bridge)),
                const Divider(),
                _Footer(state: state, bridge: bridge),
              ]),
            ),
            if (state.dragHover)
              Positioned.fill(
                child: IgnorePointer(
                  child: Container(
                    decoration: BoxDecoration(
                      color: Palette.accent.withValues(alpha: 0.10),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: Palette.accent, width: 2),
                    ),
                    alignment: Alignment.center,
                    child: Text('Drop to add stems', style: Type.title.copyWith(color: Palette.accent, fontSize: 22)),
                  ),
                ),
              ),
          ]),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final review = state.tracks.where((t) => t.needsReview).length;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 14),
      child: Row(children: [
        const Icon(LucideIcons.audioLines, size: 20, color: Palette.accent),
        const SizedBox(width: 10),
        const Text('TrackMate', style: Type.title),
        const SizedBox(width: 10),
        if (state.tracks.isNotEmpty)
          Text('${state.tracks.length} track${state.tracks.length == 1 ? '' : 's'}', style: Type.bodyMuted),
        // Right-aligned; the tempo control sits in the top right corner.
        Expanded(
          child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            if (review > 0) ...[
              const Icon(LucideIcons.circleAlert, size: 16, color: reviewText),
              const SizedBox(width: 6),
              Text('$review to review', style: Type.label.copyWith(color: reviewText)),
              const SizedBox(width: 16),
            ],
            Flexible(child: _EngineStatus(state: state)),
            const SizedBox(width: 16),
            TempoButton(state: state),
          ]),
        ),
      ]),
    );
  }
}

class _EngineStatus extends StatelessWidget {
  const _EngineStatus({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final (IconData icon, Color color, String text, String tip) = switch (state.engineState) {
      EngineState.starting => (LucideIcons.loader, Palette.muted, 'Starting engine', ''),
      EngineState.error => (LucideIcons.circleAlert, Palette.error, 'Engine error', state.engineError ?? ''),
      EngineState.ready => () {
          final downloading = state.models.values.where((m) => (m as Map)['state'] == 'downloading').toList();
          if (downloading.isNotEmpty) {
            final p = downloading.map((m) => (m as Map)['progress'] as num).reduce((a, b) => a + b) / downloading.length;
            return (LucideIcons.download, Palette.muted, 'Downloading models ${(p * 100).toStringAsFixed(0)}%', '');
          }
          // Plain words instead of the engine's layer letters A-D.
          final ai = state.layers['C'] ?? false;
          final sound = state.layers['D'] ?? false;
          final text = ai && sound
              ? 'Recognition ready'
              : !ai && !sound
                  ? 'Recognising by name list only'
                  : !sound
                      ? 'Sound recognition not ready'
                      : 'AI name reading not ready';
          return (ai && sound ? LucideIcons.sparkles : LucideIcons.circleAlert, ai && sound ? Palette.muted : Palette.review,
              text, recognitionHelp);
        }(),
    };
    return Tooltip(
      message: tip,
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 15, color: color),
        const SizedBox(width: 6),
        Flexible(child: Text(text, style: Type.label.copyWith(color: color), overflow: TextOverflow.ellipsis)),
      ]),
    );
  }
}

/// "Pro Tools session: name (48 kHz)" with a refresh button, like a sub-header.
class _SessionBar extends StatelessWidget {
  const _SessionBar({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final session = state.session?['session'] as Map<String, dynamic>?;
    final connected = session != null;
    final text = connected
        ? 'Pro Tools session: ${session['name']}  ·  ${((session['sample_rate'] as num?) ?? 0) / 1000} kHz'
        : state.sessionError ?? (state.session == null ? 'Pro Tools: checking…' : 'Pro Tools: no session open');
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 10, 12, 6),
      child: Row(children: [
        Icon(connected ? LucideIcons.link2 : LucideIcons.link2Off, size: 15, color: connected ? Palette.muted : Palette.review),
        const SizedBox(width: 8),
        Flexible(child: Text(text, style: Type.bodyMuted, overflow: TextOverflow.ellipsis)),
        const SizedBox(width: 4),
        IconButton(
          tooltip: 'Read the Pro Tools session again',
          iconSize: 15,
          icon: const Icon(LucideIcons.rotateCw),
          onPressed: state.engineState == EngineState.ready ? state.refreshSession : null,
        ),
      ]),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.state, this.bridge});
  final AppState state;
  final NativeBridge? bridge;

  @override
  Widget build(BuildContext context) {
    if (state.engineState == EngineState.error) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(LucideIcons.triangleAlert, size: 32, color: Palette.review),
          const SizedBox(height: 12),
          const Text('The TrackMate engine could not start', style: Type.title),
          const SizedBox(height: 6),
          SizedBox(
            width: 520,
            child: Text('${state.engineError}', textAlign: TextAlign.center, style: Type.caption, maxLines: 4,
                overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            key: const ValueKey('restart-engine'),
            icon: const Icon(LucideIcons.rotateCw, size: 16),
            label: const Text('Restart engine'),
            onPressed: state.restartEngine == null ? null : () => state.restartEngine!(),
          ),
        ]),
      );
    }
    if (state.tracks.isEmpty) return _EmptyState(state: state, bridge: bridge);
    return Column(children: [
      const TrackHeader(),
      Expanded(
        child: ListView.builder(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          itemCount: state.tracks.length,
          itemBuilder: (_, i) => Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: TrackRowView(key: ObjectKey(state.tracks[i]), row: state.tracks[i], state: state),
          ),
        ),
      ),
    ]);
  }
}

/// Faint placeholder rows behind a single call to action.
class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.state, this.bridge});
  final AppState state;
  final NativeBridge? bridge;

  @override
  Widget build(BuildContext context) {
    final ready = state.engineState == EngineState.ready && bridge != null;
    return Stack(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 18, 12, 12),
        child: Column(children: [
          for (var i = 0; i < 7; i++)
            Container(
              height: 46,
              margin: const EdgeInsets.only(bottom: 6),
              decoration: BoxDecoration(color: Palette.surface, borderRadius: BorderRadius.circular(10)),
            ),
        ]),
      ),
      Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          FilledButton.icon(
            style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 16),
                textStyle: const TextStyle(fontFamily: Type.family, fontSize: 16, fontWeight: FontWeight.w600)),
            icon: const Icon(LucideIcons.folderOpen, size: 18),
            label: const Text('Add audio files'),
            onPressed: ready ? () async => state.addFiles(await bridge!.pickFiles()) : null,
          ),
          const SizedBox(height: 12),
          const Text('or drag stems and folders here', style: Type.bodyMuted),
        ]),
      ),
    ]);
  }
}

class _Footer extends StatelessWidget {
  const _Footer({required this.state, this.bridge});
  final AppState state;
  final NativeBridge? bridge;

  @override
  Widget build(BuildContext context) {
    final ready = state.engineState == EngineState.ready;
    final status = state.message ??
        (state.tracks.isEmpty
            ? (ready ? 'Ready for audio files' : 'Waiting for the engine…')
            : 'Check the names, then preview and apply');
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 14, 12),
      child: Row(children: [
        if (state.busy) ...[
          const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Palette.accent)),
          const SizedBox(width: 10),
        ],
        Expanded(child: Text(status, key: const ValueKey('status-message'), style: Type.bodyMuted, overflow: TextOverflow.ellipsis)),
        Tooltip(
          message: 'Off: words the app could not recognise and Pro Tools suffixes\n'
              '(take and clip numbers such as _04-01, AudioSuite tags such as -TCEx_01)\n'
              'are removed from the new names. On: they are kept.',
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Transform.scale(
              scale: 0.8,
              child: Switch(
                key: const ValueKey('keep-unknown'),
                value: state.keepUnknown,
                onChanged: state.busy ? null : state.setKeepUnknown,
              ),
            ),
            const Text('Keep unrecognised words', style: Type.label),
          ]),
        ),
        const SizedBox(width: 12),
        TextButton(onPressed: state.tracks.isEmpty || state.busy ? null : state.clear, child: const Text('Clear')),
        const SizedBox(width: 6),
        OutlinedButton.icon(
          icon: const Icon(LucideIcons.plus, size: 16),
          label: const Text('Add files'),
          onPressed: ready && bridge != null && !state.busy ? () async => state.addFiles(await bridge!.pickFiles()) : null,
        ),
        const SizedBox(width: 8),
        FilledButton.icon(
          key: const ValueKey('apply-button'),
          icon: const Icon(LucideIcons.listChecks, size: 16),
          label: const Text('Preview & apply'),
          // Enabled without a session too: the click explains what is missing.
          onPressed: ready && state.tracks.isNotEmpty && !state.busy ? () => previewAndApply(context, state) : null,
        ),
      ]),
    );
  }
}
