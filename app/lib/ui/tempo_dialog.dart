import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../app_state.dart';
import '../models.dart';
import 'theme.dart';

/// Header display (top right): the BPM, detected on its own once the stems are recognised. It is
/// only a display; the tempo is chosen in the step before the import (Preview & apply).
class TempoIndicator extends StatelessWidget {
  const TempoIndicator({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    if (state.tempoBusy && state.tempo == null) {
      return const Row(key: ValueKey('tempo-detecting'), mainAxisSize: MainAxisSize.min, children: [
        SizedBox(width: 13, height: 13, child: CircularProgressIndicator(strokeWidth: 2, color: Palette.accent)),
        SizedBox(width: 8),
        Text('Detecting tempo…', style: Type.label),
      ]);
    }
    final tempo = state.tempo;
    final error = state.tempoError;
    final (Widget main, String detail, String tip) = tempo != null
        ? (
            Text(state.tempoLabel,
                key: const ValueKey('tempo-bpm'),
                style: Type.body.copyWith(fontWeight: FontWeight.w600, fontFeatures: const [FontFeature.tabularFigures()])),
            switch (state.tempoMode) { 'constant' => 'Constant', 'variable' => 'Tempo map', _ => 'Not imported' },
            'Detected tempo: you choose how it is imported in Preview & apply',
          )
        : error != null
            ? (
                Text(error.code == 'tempo_model_not_ready' ? 'Tempo model downloading' : 'No BPM found',
                    style: Type.label.copyWith(color: Palette.review)),
                '',
                error.message,
              )
            : (const Text('– BPM', style: Type.label), '', 'The tempo is detected when stems are added');
    final applied = state.tempoResult?['applied'] == true;
    // Plain icon and text like the recognition status next to it: a display, not a button.
    return Tooltip(
      message: tip,
      child: Row(key: const ValueKey('tempo-chip'), mainAxisSize: MainAxisSize.min, children: [
        Icon(LucideIcons.metronome, size: 15, color: tempo != null ? Palette.accent : Palette.muted),
        const SizedBox(width: 7),
        main,
        if (detail.isNotEmpty) ...[
          const SizedBox(width: 7),
          Text(detail, style: Type.caption),
        ],
        if (applied) ...[
          const SizedBox(width: 6),
          const Icon(LucideIcons.check, size: 14, color: Palette.ok),
        ],
      ]),
    );
  }
}

/// The tempo step of Preview & apply, before the preview: waits for a detection still running,
/// then the user chooses constant tempo, tempo map or keeping the session tempo. True to go on.
Future<bool> chooseTempo(BuildContext context, AppState state) async =>
    await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _TempoDialog(state: state),
    ) ==
    true;

class _TempoDialog extends StatefulWidget {
  const _TempoDialog({required this.state});
  final AppState state;

  @override
  State<_TempoDialog> createState() => _TempoDialogState();
}

class _TempoDialogState extends State<_TempoDialog> {
  AppState get state => widget.state;
  late final _bpm = TextEditingController(text: '${state.tempoBpm}');

  @override
  void dispose() {
    _bpm.dispose();
    super.dispose();
  }

  void _setBpm(int v) {
    state.setTempoBpm(v);
    _bpm.text = '${state.tempoBpm}';
  }

  Future<void> _retry() async {
    await state.detectTempo(again: true);
    _bpm.text = '${state.tempoBpm}';
  }

  static String _clock(double s) => '${s ~/ 60}:${(s % 60).floor().toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: state,
      builder: (context, _) {
        final t = state.tempo;
        final detecting = state.tempoBusy && t == null;
        return AlertDialog(
          title: Row(children: [
            const Icon(LucideIcons.metronome, size: 20, color: Palette.accent),
            const SizedBox(width: 10),
            const Text('Tempo for this import'),
          ]),
          content: SizedBox(
            width: 600,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Choose how the session tempo is set. It is imported together with the tracks.',
                  style: Type.bodyMuted),
              const SizedBox(height: 14),
              if (detecting)
                const Row(key: ValueKey('tempo-dialog-detecting'), children: [
                  SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Palette.accent)),
                  SizedBox(width: 10),
                  Text('Detecting the tempo in the drum stems…', style: Type.body),
                ])
              else if (t == null)
                _NoTempo(state: state, onRetry: _retry)
              else
                ..._settings(t),
            ]),
          ),
          actions: [
            TextButton(
                key: const ValueKey('tempo-cancel'),
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancel')),
            FilledButton.icon(
              key: const ValueKey('tempo-continue'),
              icon: const Icon(LucideIcons.arrowRight, size: 16),
              label: Text(state.tempoWillImport ? 'Continue with ${state.tempoLabel}' : 'Continue without tempo'),
              onPressed: state.tempoBusy ? null : () => Navigator.pop(context, true),
            ),
          ],
        );
      },
    );
  }

  List<Widget> _settings(TempoInfo t) {
    final f = state.tempoFactor;
    final kind = switch (t.sourceKind) { 'drums' => 'drum', 'rhythm' => 'rhythm', _ => '' };
    final sources = '${t.sources.length} ${kind.isEmpty ? '' : '$kind '}stem${t.sources.length == 1 ? '' : 's'}';
    final none = state.tempoMode == 'none';
    return [
      Text(state.tempoLabel, key: const ValueKey('tempo-dialog-bpm'),
          style: Type.title.copyWith(fontSize: 34, fontWeight: FontWeight.w600)),
      const SizedBox(height: 4),
      Text(
        t.steady
            ? 'Steady beat: every beat is within ${t.gridErrorMs.round()} ms of a ${(t.bpm * f).toStringAsFixed(2)} BPM grid.'
            : 'The tempo moves between ${(t.bpmMin * f).round()} and ${(t.bpmMax * f).round()} BPM '
                '(average ${(t.bpm * f).toStringAsFixed(1)}).',
        style: Type.bodyMuted,
      ),
      const SizedBox(height: 2),
      Tooltip(
        message: t.sources.map((s) => s.split(RegExp(r'[\\/]')).last).join('\n'),
        child: Text('Listened to $sources · ${t.beatCount} beats · ${_clock(t.duration)}'
            '${t.signatureBeats == null ? '' : ' · ${t.signatureBeats}/4'}',
            style: Type.caption),
      ),
      const SizedBox(height: 18),
      Row(children: [
        const Text('Import as', style: Type.label),
        const SizedBox(width: 8),
        Text('suggested: ${t.suggestedMode == 'constant' ? 'constant tempo' : 'tempo map'}', style: Type.caption),
      ]),
      const SizedBox(height: 6),
      SegmentedButton<String>(
        key: const ValueKey('tempo-mode'),
        showSelectedIcon: false,
        segments: const [
          ButtonSegment(value: 'constant', icon: Icon(LucideIcons.equal, size: 15), label: Text('Constant tempo')),
          ButtonSegment(value: 'variable', icon: Icon(LucideIcons.activity, size: 15), label: Text('Tempo map')),
          ButtonSegment(value: 'none', icon: Icon(LucideIcons.ban, size: 15), label: Text('Keep session tempo')),
        ],
        selected: {state.tempoMode},
        onSelectionChanged: state.tempoBusy ? null : (v) => state.setTempoMode(v.first),
      ),
      const SizedBox(height: 14),
      if (!none) ...[
        const Text('Beat', style: Type.label),
        const SizedBox(height: 6),
        SegmentedButton<double>(
          key: const ValueKey('tempo-factor'),
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: 0.5, label: Text('½× half time')),
            ButtonSegment(value: 1, label: Text('As detected')),
            ButtonSegment(value: 2, label: Text('2× double time')),
          ],
          selected: {f},
          onSelectionChanged: state.tempoBusy
              ? null
              : (v) {
                  state.setTempoFactor(v.first);
                  _bpm.text = '${state.tempoBpm}';
                },
        ),
        const SizedBox(height: 12),
      ],
      if (state.tempoMode == 'constant')
        Row(children: [
          IconButton(
            tooltip: '1 BPM slower',
            icon: const Icon(LucideIcons.minus, size: 16),
            onPressed: () => _setBpm(state.tempoBpm - 1),
          ),
          SizedBox(
            width: 72,
            child: TextField(
              key: const ValueKey('tempo-bpm-field'),
              controller: _bpm,
              textAlign: TextAlign.center,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(3)],
              onSubmitted: (v) => _setBpm(int.tryParse(v) ?? state.tempoBpm),
              onChanged: (v) {
                final n = int.tryParse(v);
                if (n != null && n >= 20 && n <= 400) state.setTempoBpm(n);
              },
            ),
          ),
          IconButton(
            tooltip: '1 BPM faster',
            icon: const Icon(LucideIcons.plus, size: 16),
            onPressed: () => _setBpm(state.tempoBpm + 1),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text('BPM for the whole session (the average, ${state.tempoAverage.toStringAsFixed(2)}, rounded)',
                style: Type.caption),
          ),
        ])
      else if (state.tempoMode == 'variable')
        const Text('One tempo per bar, so every bar line falls on the downbeat heard in the stems.', style: Type.caption)
      else
        const Text('The session keeps its current tempo.', style: Type.caption),
      if (!none) ...[
        const SizedBox(height: 14),
        const Text(
            'After the tracks, Pro Tools asks in "MIDI Import Options": keep "Import tempo map from MIDI File" ticked '
            'and press OK. TrackMate then checks the session tempo.',
            style: Type.caption),
      ],
    ];
  }
}

/// Why there is no tempo: no beat in the stems, the model still downloading, or an error.
class _NoTempo extends StatelessWidget {
  const _NoTempo({required this.state, required this.onRetry});
  final AppState state;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    final e = state.tempoError;
    final text = switch (e?.code) {
      'tempo_model_not_ready' => 'The tempo model is still downloading, so the session tempo stays as it is this time.',
      'no_beats' => 'No steady beat was found in the stems (TrackMate listens to the drums and percussion, or bass, '
          'guitars, keys and synths when there are none). The session tempo stays as it is.',
      _ => 'The tempo could not be detected${e == null ? '' : ': ${e.message}'}. The session tempo stays as it is.',
    };
    return Column(key: const ValueKey('tempo-error'), crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Icon(LucideIcons.circleAlert, size: 18, color: Palette.review),
        const SizedBox(width: 10),
        Expanded(child: Text(text, style: Type.body)),
      ]),
      if (e?.code != 'tempo_model_not_ready') ...[
        const SizedBox(height: 10),
        TextButton.icon(
          key: const ValueKey('tempo-retry'),
          icon: const Icon(LucideIcons.rotateCw, size: 15),
          label: const Text('Detect again'),
          onPressed: state.tempoBusy ? null : onRetry,
        ),
      ],
    ]);
  }
}
