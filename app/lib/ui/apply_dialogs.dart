import 'package:flutter/material.dart';

import '../alerts.dart';
import '../app_state.dart';
import 'alert_dialog.dart';

/// Shows [alert] and runs its action; true when the user asked to try again.
Future<bool> _handle(BuildContext context, AppState state, AppAlert alert) async {
  if (!context.mounted) return false;
  final again = await showAlert(context, alert);
  if (again && alert.action == AlertAction.restartEngine) await state.restartEngine?.call();
  return again;
}

/// Check Pro Tools -> preview (dry run) -> confirm -> apply -> results. Nothing is
/// sent to Pro Tools before the user has seen the folders and names. Every failure becomes a
/// dialog that says what to do; "Try again" starts over from the Pro Tools check.
Future<void> previewAndApply(BuildContext context, AppState state) async {
  // Pro Tools must be running with a session open.
  while (true) {
    await state.refreshSession();
    final problem = state.sessionProblem;
    if (problem == null) break;
    if (!context.mounted || !await _handle(context, state, problem)) return;
  }
  if (!context.mounted) return;
  Map<String, dynamic> plan;
  try {
    plan = await state.preview();
  } catch (e) {
    if (context.mounted && await _handle(context, state, AppAlert.fromError(e, doing: 'preview the import'))) {
      if (context.mounted) return previewAndApply(context, state);
    }
    return;
  }
  if (!context.mounted) return;
  final session = plan['session'] as Map<String, dynamic>;
  final folders = plan['plan'] as List;
  final catalog = state.catalog!;
  final muted = Theme.of(context).colorScheme.onSurfaceVariant;
  final newFolders = folders.where((f) => f['exists'] != true).length;
  final withTempo = state.tempo != null && state.tempoWithApply;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text('Apply to Pro Tools: ${session['name']}'),
      content: SizedBox(
        width: 560,
        height: 420,
        child: ListView(children: [
          Text('Creates $newFolders folder${newFolders == 1 ? '' : 's'} and imports ${state.tracks.length} '
              'track${state.tracks.length == 1 ? '' : 's'} (converted to the session rate, '
              '${session['sample_rate']} Hz).'),
          if (withTempo) ...[
            const SizedBox(height: 8),
            Text(
                'Then sets the tempo: ${state.tempoMode == 'constant' ? '${state.tempoLabel}, constant' : 'tempo map, ${state.tempoLabel}'}. '
                'Pro Tools asks in "MIDI Import Options": keep "Import tempo map from MIDI File" ticked and press OK.',
                key: const ValueKey('apply-tempo-line')),
          ],
          const SizedBox(height: 12),
          for (final f in folders) ...[
            Row(children: [
              Container(width: 14, height: 14, color: Color(catalog.color(f['color_index'] as int))),
              const SizedBox(width: 8),
              Text(f['folder'] as String, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(width: 8),
              Text(f['exists'] == true ? '(existing folder)' : '(new)', style: TextStyle(color: muted)),
            ]),
            for (final t in f['tracks'] as List)
              Padding(
                padding: const EdgeInsets.only(left: 24, top: 2),
                child: Row(children: [
                  Container(width: 10, height: 10, color: Color(catalog.color(t['color_index'] as int))),
                  const SizedBox(width: 8),
                  Expanded(child: Text(t['final_name'] as String)),
                  if (t['mono'] == true) Text('to mono', style: TextStyle(fontSize: 12, color: muted)),
                ]),
              ),
            const SizedBox(height: 8),
          ],
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('confirm-apply'),
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('Apply to Pro Tools'),
        ),
      ],
    ),
  );
  if (ok != true || !context.mounted) return;
  Map<String, dynamic> res;
  try {
    res = await state.applyToProTools();
  } catch (e) {
    if (context.mounted && await _handle(context, state, AppAlert.fromError(e, doing: 'apply to Pro Tools'))) {
      if (context.mounted) return previewAndApply(context, state);
    }
    return;
  }
  // The tempo comes after the tracks: the tracks are in the session even if this fails.
  String tempoText = '';
  if (withTempo && context.mounted) {
    try {
      final t = await state.applyTempo();
      tempoText = t['applied'] == true
          ? '\n\nTempo set: ${state.tempoLabel}.'
          : '\n\nThe tempo was not changed: the MIDI Import Options dialog was cancelled or '
              '"Import tempo map from MIDI File" was unticked. Use the BPM button to import it again.';
    } catch (e) {
      tempoText = '\n\nThe tempo was not imported: ${AppAlert.fromError(e).title}.';
    }
  }
  if (!context.mounted) return;
  final results = res['results'] as List;
  final failed = results.where((r) =>
      !(r['name_ok'] == true && r['folder_ok'] == true && r['color_ok'] == true && (r['errors'] as List).isEmpty));
  await showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(res['ok'] == true ? 'Done' : 'Done, with problems'),
      content: Text((res['ok'] == true
              ? '${results.length} tracks imported and verified (name, folder, colour) in ${res['seconds']} s.'
              : '${failed.length} tracks did not pass verification:\n'
                  '${failed.map((r) => '${r['final_name']}: ${r['errors']}').join('\n')}') +
          tempoText),
      actions: [FilledButton(key: const ValueKey('close-result'), onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
    ),
  );
}
