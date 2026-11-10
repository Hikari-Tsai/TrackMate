import 'dart:async';

import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../alerts.dart';
import '../app_state.dart';
import 'alert_dialog.dart';
import 'pickers.dart';
import 'tempo_dialog.dart';
import 'theme.dart';

/// Shows [alert] and runs its action; true when the user asked to try again.
Future<bool> _handle(BuildContext context, AppState state, AppAlert alert) async {
  if (!context.mounted) return false;
  final again = await showAlert(context, alert);
  if (again && alert.action == AlertAction.restartEngine) await state.restartEngine?.call();
  return again;
}

/// Check Pro Tools -> tempo -> preview (dry run) -> confirm -> apply tracks, then tempo -> results.
/// Nothing is sent to Pro Tools before the user has chosen the tempo and seen the folders and
/// names. Every failure becomes a dialog that says what to do; "Try again" starts over from the
/// Pro Tools check.
Future<void> previewAndApply(BuildContext context, AppState state) async {
  // Pro Tools must be running with a session open.
  while (true) {
    await state.refreshSession();
    final problem = state.sessionProblem;
    if (problem == null) break;
    if (!context.mounted || !await _handle(context, state, problem)) return;
  }
  if (!context.mounted) return;
  // The tempo is always chosen before the import. It was detected in the background; this
  // detects again when the list or a category changed since.
  unawaited(state.detectTempo());
  if (!await chooseTempo(context, state) || !context.mounted) return;
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
  final withTempo = state.tempoWillImport;
  final ok = await showDialog<bool>(
    context: context,
    builder: (_) => _PreviewDialog(state: state, plan: plan),
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
  // The tempo comes after the tracks: the tracks are in the session even if this fails, and the
  // result dialog can import the tempo again (when Pro Tools' dialog was cancelled).
  Map<String, dynamic>? tempoRes;
  Object? tempoErr;
  Future<void> importTempo() async {
    try {
      tempoRes = await state.applyTempo();
      tempoErr = null;
    } catch (e) {
      tempoErr = e;
    }
  }

  if (withTempo) await importTempo();
  final results = res['results'] as List;
  final failed = results.where((r) =>
      !(r['name_ok'] == true && r['folder_ok'] == true && r['color_ok'] == true && (r['errors'] as List).isEmpty));
  final tracksText = res['ok'] == true
      ? '${results.length} tracks imported and verified (name, folder, colour) in ${res['seconds']} s.'
      : '${failed.length} tracks did not pass verification:\n'
          '${failed.map((r) => '${r['final_name']}: ${r['errors']}').join('\n')}';
  while (true) {
    if (!context.mounted) return;
    final tempoOk = tempoRes?['applied'] == true;
    final tempoText = !withTempo
        ? 'The session tempo was not changed.'
        : tempoOk
            ? 'Tempo set: ${state.tempoLabel} (checked in Pro Tools).'
            : tempoErr != null
                ? 'The tempo was not imported: ${AppAlert.fromError(tempoErr!).title}.'
                : 'The tempo was not changed: the MIDI Import Options dialog was cancelled or '
                    '"Import tempo map from MIDI File" was unticked.';
    final again = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: Text(res['ok'] == true && (!withTempo || tempoOk) ? 'Done' : 'Done, with problems'),
        content: Text('$tracksText\n\n$tempoText', key: const ValueKey('result-text')),
        actions: [
          if (withTempo && !tempoOk)
            TextButton(
                key: const ValueKey('retry-tempo'),
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Import tempo again')),
          FilledButton(key: const ValueKey('close-result'), onPressed: () => Navigator.pop(ctx, false), child: const Text('OK')),
        ],
      ),
    );
    if (again != true) break;
    await importTempo();
  }
}

/// The preview (dry run): the folders, every track's final name, mono conversions and the
/// tempo. Each folder has a picker: create it new, or put its tracks into a Basic Folder the
/// session already has. A choice runs the dry run again, so the names and the new / existing
/// marks are always the engine's.
class _PreviewDialog extends StatefulWidget {
  const _PreviewDialog({required this.state, required this.plan});
  final AppState state;
  final Map<String, dynamic> plan;

  @override
  State<_PreviewDialog> createState() => _PreviewDialogState();
}

class _PreviewDialogState extends State<_PreviewDialog> {
  AppState get state => widget.state;
  late Map<String, dynamic> plan = widget.plan;
  bool loading = false;
  String? error;

  Future<void> _choose(BuildContext anchor, String category) async {
    final existing = state.existingFolders;
    final current = state.folderChoices.containsKey(category) ? state.folderChoices[category] ?? '' : null;
    Widget item(String value, IconData icon, String label) => Row(children: [
          Icon(icon, size: 15, color: Palette.muted),
          const SizedBox(width: 10),
          Expanded(
            child: Text(label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontWeight: value == current ? FontWeight.w600 : FontWeight.w400)),
          ),
          if (value == current) const Icon(LucideIcons.check, size: 14, color: Palette.accent),
        ]);
    final choice = await showMenuBelow<String>(anchor, maxWidth: 320, [
      PopupMenuItem(
          key: ValueKey('folder-item-$category-new'),
          value: '',
          height: 34,
          child: item('', LucideIcons.folderPlus, 'New folder')),
      if (existing.isNotEmpty) const PopupMenuDivider(),
      for (final f in existing)
        PopupMenuItem(
            key: ValueKey('folder-item-$category-$f'),
            value: f,
            height: 34,
            child: item(f, LucideIcons.folderOpen, 'Into $f')),
    ]);
    if (choice == null || !mounted) return;
    state.setFolderChoice(category, choice.isEmpty ? null : choice);
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final p = await state.preview();
      if (mounted) setState(() => plan = p);
    } catch (e) {
      if (mounted) setState(() => error = AppAlert.fromError(e, doing: 'preview the import').title);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = plan['session'] as Map<String, dynamic>;
    final folders = plan['plan'] as List;
    final catalog = state.catalog!;
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final newFolders = folders.where((f) => f['exists'] != true).length;
    final joined = folders.length - newFolders;
    final withTempo = state.tempoWillImport;
    final n = state.tracks.length;
    return AlertDialog(
      title: Text('Apply to Pro Tools: ${session['name']}'),
      content: SizedBox(
        width: 560,
        height: 420,
        child: ListView(children: [
          Text(
              '${newFolders == 0 ? 'Creates no folder' : 'Creates $newFolders new folder${newFolders == 1 ? '' : 's'}'}'
              '${joined == 0 ? '' : ', puts tracks into $joined existing folder${joined == 1 ? '' : 's'}'}, '
              'and imports $n track${n == 1 ? '' : 's'} (converted to the session rate, ${session['sample_rate']} Hz). '
              'Each folder can be created new or be one the session already has.',
              key: const ValueKey('apply-folders-line')),
          const SizedBox(height: 8),
          Text(
              withTempo
                  ? 'Then sets the tempo: ${state.tempoMode == 'constant' ? '${state.tempoLabel}, constant' : 'tempo map, ${state.tempoLabel}'}. '
                      'Pro Tools asks in "MIDI Import Options": keep "Import tempo map from MIDI File" ticked and press OK.'
                  : 'The session tempo is not changed.',
              key: const ValueKey('apply-tempo-line')),
          const SizedBox(height: 12),
          if (loading) const LinearProgressIndicator(minHeight: 2),
          if (error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(error!, key: const ValueKey('apply-folders-error'), style: const TextStyle(color: Palette.review)),
            ),
          for (final f in folders) ...[
            Row(children: [
              Container(width: 14, height: 14, color: Color(catalog.color(f['color_index'] as int))),
              const SizedBox(width: 8),
              Text(f['folder'] as String, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(width: 8),
              Builder(
                builder: (ctx) => InkWell(
                  key: ValueKey('folder-choice-${f['category']}'),
                  borderRadius: BorderRadius.circular(8),
                  onTap: loading ? null : () => _choose(ctx, f['category'] as String),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(f['exists'] == true ? LucideIcons.folderOpen : LucideIcons.folderPlus, size: 14, color: muted),
                      const SizedBox(width: 6),
                      Text(f['exists'] == true ? 'existing folder' : 'new folder', style: TextStyle(color: muted)),
                      const SizedBox(width: 4),
                      Icon(LucideIcons.chevronDown, size: 14, color: muted),
                    ]),
                  ),
                ),
              ),
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
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('confirm-apply'),
          onPressed: loading ? null : () => Navigator.pop(context, true),
          child: const Text('Apply to Pro Tools'),
        ),
      ],
    );
  }
}
