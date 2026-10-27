import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../alerts.dart';
import '../app_state.dart';
import 'theme.dart';

/// Header control: "Detect BPM", then the detected BPM. Detecting opens the tempo dialog.
class TempoButton extends StatelessWidget {
  const TempoButton({super.key, required this.state});
  final AppState state;

  Future<void> _detect(BuildContext context) async {
    await state.detectTempo();
    if (state.tempo != null && context.mounted) await showTempoDialog(context, state);
  }

  @override
  Widget build(BuildContext context) {
    if (state.tempoBusy && state.tempo == null) {
      return const Row(mainAxisSize: MainAxisSize.min, children: [
        SizedBox(width: 13, height: 13, child: CircularProgressIndicator(strokeWidth: 2, color: Palette.accent)),
        SizedBox(width: 8),
        Text('Detecting tempo…', style: Type.label),
      ]);
    }
    final tempo = state.tempo;
    if (tempo == null) {
      final ready = state.engineState == EngineState.ready && state.tracks.isNotEmpty && !state.busy;
      final why = !state.tempoModelReady
          ? 'The tempo model is still downloading'
          : state.tracks.isEmpty
              ? 'Add stems first'
              : 'Find the tempo in the drum and percussion stems';
      return Tooltip(
        message: why,
        child: OutlinedButton.icon(
          key: const ValueKey('detect-bpm'),
          // As tall as the title, so the header keeps its height.
          style: OutlinedButton.styleFrom(
            minimumSize: const Size(0, 28),
            padding: const EdgeInsets.symmetric(horizontal: 10),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            textStyle: Type.label,
          ),
          icon: const Icon(LucideIcons.metronome, size: 15),
          label: const Text('Detect BPM'),
          onPressed: ready && state.tempoModelReady ? () => _detect(context) : null,
        ),
      );
    }
    final applied = state.tempoResult?['applied'] == true;
    return Tooltip(
      message: 'Tempo settings and import to Pro Tools',
      child: InkWell(
        key: const ValueKey('tempo-chip'),
        borderRadius: BorderRadius.circular(8),
        onTap: () => showTempoDialog(context, state),
        child: Container(
          height: 28,
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            color: Palette.raised,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Palette.border),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            const Icon(LucideIcons.metronome, size: 15, color: Palette.accent),
            const SizedBox(width: 7),
            Text(state.tempoLabel,
                key: const ValueKey('tempo-bpm'),
                style: Type.body.copyWith(fontWeight: FontWeight.w600, fontFeatures: const [FontFeature.tabularFigures()])),
            const SizedBox(width: 7),
            Text(state.tempoMode == 'constant' ? 'Constant' : 'Tempo map', style: Type.caption),
            if (applied) ...[
              const SizedBox(width: 6),
              const Icon(LucideIcons.check, size: 14, color: Palette.ok),
            ],
          ]),
        ),
      ),
    );
  }
}

Future<void> showTempoDialog(BuildContext context, AppState state) =>
    showDialog<void>(context: context, builder: (_) => _TempoDialog(state: state));

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

  Future<void> _import() async {
    await state.refreshSession();
    final problem = state.sessionProblem;
    if (problem != null) {
      state.alert(problem);
      return;
    }
    try {
      await state.applyTempo();
    } catch (e) {
      state.alert(AppAlert.fromError(e, doing: 'import the tempo'));
    }
  }

  Future<void> _save() async {
    try {
      await state.applyTempo(toProTools: false);
    } catch (e) {
      state.alert(AppAlert.fromError(e, doing: 'save the tempo MIDI'));
    }
  }

  static String _clock(double s) => '${s ~/ 60}:${(s % 60).floor().toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: state,
      builder: (context, _) {
        final t = state.tempo;
        if (t == null) return const SizedBox.shrink();
        final f = state.tempoFactor;
        final kind = switch (t.sourceKind) { 'drums' => 'drum', 'rhythm' => 'rhythm', _ => '' };
        final sources = '${t.sources.length} ${kind.isEmpty ? '' : '$kind '}stem${t.sources.length == 1 ? '' : 's'}';
        final result = state.tempoResult;
        return AlertDialog(
          title: const Row(children: [
            Icon(LucideIcons.metronome, size: 20, color: Palette.accent),
            SizedBox(width: 10),
            Text('Tempo'),
          ]),
          content: SizedBox(
            width: 520,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(state.tempoLabel, key: const ValueKey('tempo-dialog-bpm'),
                  style: Type.title.copyWith(fontSize: 34, fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              Text(
                t.steady
                    ? 'Steady beat: every beat is within ${t.gridErrorMs.round()} ms of a '
                        '${(t.bpm * f).toStringAsFixed(2)} BPM grid.'
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
              const SizedBox(height: 16),
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
                  ButtonSegment(value: 'variable', icon: Icon(LucideIcons.activity, size: 15), label: Text('Tempo map (variable)')),
                ],
                selected: {state.tempoMode},
                onSelectionChanged: state.tempoBusy ? null : (v) => state.setTempoMode(v.first),
              ),
              const SizedBox(height: 12),
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
              else
                const Text('One tempo per bar, so every bar line falls on the downbeat heard in the stems.',
                    style: Type.caption),
              const SizedBox(height: 14),
              const Text(
                  'Pro Tools asks in "MIDI Import Options": keep "Import tempo map from MIDI File" ticked and press OK. '
                  'TrackMate then checks the session tempo.',
                  style: Type.caption),
              const SizedBox(height: 6),
              Row(children: [
                Checkbox(
                  key: const ValueKey('tempo-with-apply'),
                  value: state.tempoWithApply,
                  onChanged: (v) => state.setTempoWithApply(v ?? false),
                ),
                const Flexible(child: Text('Also import the tempo with Preview & apply', style: Type.body)),
              ]),
              if (state.tempoBusy) ...[
                const SizedBox(height: 8),
                Row(children: [
                  const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Palette.accent)),
                  const SizedBox(width: 10),
                  Expanded(child: Text(state.message ?? 'Working…', style: Type.bodyMuted)),
                ]),
              ] else if (result != null) ...[
                const SizedBox(height: 8),
                _ResultLine(result: result, label: state.tempoLabel),
              ],
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
            OutlinedButton.icon(
              key: const ValueKey('tempo-save'),
              icon: const Icon(LucideIcons.fileMusic, size: 16),
              label: const Text('Save MIDI'),
              onPressed: state.tempoBusy ? null : _save,
            ),
            FilledButton.icon(
              key: const ValueKey('tempo-import'),
              icon: const Icon(LucideIcons.import, size: 16),
              label: const Text('Import to Pro Tools'),
              onPressed: state.tempoBusy ? null : _import,
            ),
          ],
        );
      },
    );
  }
}

class _ResultLine extends StatelessWidget {
  const _ResultLine({required this.result, required this.label});
  final Map<String, dynamic> result;
  final String label;

  @override
  Widget build(BuildContext context) {
    final file = (result['midi_path'] as String).split(RegExp(r'[\\/]')).last;
    final (IconData icon, Color color, String text) = result['imported'] != true
        ? (LucideIcons.fileCheck, Palette.ok, 'Saved "$file" next to the stems.')
        : result['applied'] == true
            ? (LucideIcons.circleCheck, Palette.ok,
                'Pro Tools tempo is now $label (checked at bar ${(result['pro_tools_position'] as String).split('|').first.trim()}).')
            : (LucideIcons.circleAlert, Palette.review,
                'Pro Tools kept its tempo: the dialog was cancelled or "Import tempo map from MIDI File" was unticked. '
                    'Import again to retry.');
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Icon(icon, size: 16, color: color),
      const SizedBox(width: 8),
      Expanded(
        child: SelectableText(text, key: const ValueKey('tempo-result'), style: Type.body.copyWith(color: color)),
      ),
    ]);
  }
}
