import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../app_state.dart';
import '../engine/engine_api.dart';
import 'theme.dart';

/// What each model does, in the order of the dialog. The engine names the models by repository;
/// the user sees the layer they power.
class ModelInfo {
  const ModelInfo(this.title, this.detail, this.icon);
  final String title; // the layer, in plain words
  final String detail; // what it is used for and the model's name
  final IconData icon;
}

const modelInfo = {
  'qwen3_embedding': ModelInfo('AI name reading', 'Reads track names the dictionary does not know (Qwen3 Embedding)',
      LucideIcons.sparkles),
  'peav_audio': ModelInfo('Sound recognition', 'Listens to stems whose names say nothing (PE-AV)', LucideIcons.ear),
  'beat_this': ModelInfo('Tempo detection', 'Finds the BPM in the drum and rhythm stems (Beat This!)',
      LucideIcons.metronome),
};

/// "1.13 GB", "222 MB", "4.2 MB", "0 B".
String formatBytes(num bytes) {
  if (bytes >= 1e9) return '${(bytes / 1e9).toStringAsFixed(2)} GB';
  if (bytes >= 1e7) return '${(bytes / 1e6).round()} MB';
  if (bytes >= 1e6) return '${(bytes / 1e6).toStringAsFixed(1)} MB';
  if (bytes >= 1e3) return '${(bytes / 1e3).round()} kB';
  return '${bytes.round()} B';
}

/// The models window: one row per model with a checkbox, its size and its state (ready,
/// downloading with a progress bar, failed with a retry, or not downloaded), "Download all",
/// "Download selected" and "Clear models". Shown on first start while a model is missing, and
/// later from the model status in the header.
Future<void> showModelsDialog(BuildContext context, AppState state) => showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _ModelsDialog(state: state),
    );

class _ModelsDialog extends StatefulWidget {
  const _ModelsDialog({required this.state});
  final AppState state;

  @override
  State<_ModelsDialog> createState() => _ModelsDialogState();
}

class _ModelsDialogState extends State<_ModelsDialog> {
  AppState get state => widget.state;
  final _selected = <String>{};
  String? _error; // the last download or clear that failed, in words
  int? _freed; // bytes freed by the last clear

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _error = null);
    try {
      await action();
    } on EngineException catch (e) {
      setState(() => _error = e.code == 'models_downloading'
          ? 'A download is still running. Wait for it to finish, then clear the models.'
          : e.code == 'engine_unreachable'
              ? 'The engine does not answer. Restart it from the main window.'
              : e.message);
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  Future<void> _download(List<String> names) => _run(() async {
        await state.downloadModels(names);
        setState(() {
          _selected.removeAll(names);
          _freed = null;
        });
      });

  Future<void> _clear() async {
    final n = state.models.length;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const ValueKey('models-clear-confirm'),
        icon: const Icon(LucideIcons.trash2, color: Palette.review, size: 28),
        title: const Text('Delete the downloaded models?'),
        content: SizedBox(
          width: 440,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('This removes the files of all $n models from', style: Type.body),
            const SizedBox(height: 6),
            SelectableText(state.modelsDir, style: Type.mono.copyWith(color: Palette.text)),
            const SizedBox(height: 6),
            Text('and frees ${formatBytes(state.modelsOnDisk)}. Recognition then works by name list only until '
                'the models are downloaded again from this window.', style: Type.body),
          ]),
        ),
        actions: [
          TextButton(key: const ValueKey('models-clear-cancel'), onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton.icon(
            key: const ValueKey('models-clear-delete'),
            style: FilledButton.styleFrom(backgroundColor: Palette.error, foregroundColor: Palette.onAccent),
            icon: const Icon(LucideIcons.trash2, size: 16),
            label: Text('Delete ${formatBytes(state.modelsOnDisk)}'),
            onPressed: () => Navigator.pop(ctx, true),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await _run(() async {
      final freed = await state.clearModels();
      setState(() {
        _selected.clear();
        _freed = freed;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: state,
      builder: (context, _) {
        final names = [
          for (final n in modelInfo.keys) if (state.models.containsKey(n)) n,
          for (final n in state.models.keys) if (!modelInfo.containsKey(n)) n, // unknown to this app version
        ];
        final total = names.fold<int>(0, (sum, n) => sum + state.modelSize(n));
        final pending = state.modelsPending;
        final picked = [for (final n in _selected) if (pending.contains(n)) n];
        final allReady = state.modelsReady;
        final downloading = state.modelsDownloading;
        return AlertDialog(
          key: const ValueKey('models-dialog'),
          title: Row(children: [
            const Icon(LucideIcons.download, size: 20, color: Palette.accent),
            const SizedBox(width: 10),
            const Text('Recognition models'),
          ]),
          content: SizedBox(
            width: 660,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                'TrackMate downloads its models from Hugging Face once (${formatBytes(total)} in all) and keeps them on '
                'this computer. Known track names and spelling correction work without them; tick the models you want '
                'or take all of them.',
                style: Type.bodyMuted,
              ),
              const SizedBox(height: 14),
              for (final n in names) ...[
                _ModelRow(
                  name: n,
                  state: state,
                  selected: _selected.contains(n),
                  onSelected: (v) => setState(() => v ? _selected.add(n) : _selected.remove(n)),
                  onRetry: () => _download([n]),
                ),
                const SizedBox(height: 6),
              ],
              const SizedBox(height: 6),
              Row(children: [
                const Icon(LucideIcons.hardDrive, size: 14, color: Palette.faint),
                const SizedBox(width: 6),
                Expanded(
                  child: Tooltip(
                    message: state.modelsDir,
                    child: Text(
                      _freed != null
                          ? 'Freed ${formatBytes(_freed!)}. The models can be downloaded again at any time.'
                          : 'On disk: ${formatBytes(state.modelsOnDisk)}',
                      key: ValueKey(_freed != null ? 'models-cleared' : 'models-on-disk'),
                      style: Type.caption,
                    ),
                  ),
                ),
                TextButton.icon(
                  key: const ValueKey('models-clear'),
                  icon: const Icon(LucideIcons.trash2, size: 15),
                  label: const Text('Clear models'),
                  onPressed: state.modelsOnDisk > 0 && !downloading ? _clear : null,
                ),
              ]),
              if (_error != null) ...[
                const SizedBox(height: 8),
                Row(key: const ValueKey('models-error'), crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Icon(LucideIcons.circleAlert, size: 16, color: Palette.error),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_error!, style: Type.caption.copyWith(color: Palette.error))),
                ]),
              ],
            ]),
          ),
          actions: [
            TextButton(
              key: const ValueKey('models-close'),
              onPressed: () => Navigator.pop(context),
              child: Text(allReady ? 'Done' : 'Later'),
            ),
            OutlinedButton.icon(
              key: const ValueKey('models-download-selected'),
              icon: const Icon(LucideIcons.download, size: 16),
              label: Text(picked.isEmpty ? 'Download selected' : 'Download selected (${picked.length})'),
              onPressed: picked.isEmpty ? null : () => _download(picked),
            ),
            FilledButton.icon(
              key: const ValueKey('models-download-all'),
              icon: const Icon(LucideIcons.cloudDownload, size: 16),
              label: Text(allReady ? 'All models ready' : 'Download all'),
              onPressed: pending.isEmpty ? null : () => _download(pending),
            ),
          ],
        );
      },
    );
  }
}

/// One model: checkbox, purpose, size and state. A ready row is greyed out (its checkbox
/// cannot be ticked, so "Download selected" never downloads it again) but carries a green
/// "Ready" mark; a downloading one shows its own progress bar, bytes and current file; a
/// failed one shows the error and a retry button.
class _ModelRow extends StatelessWidget {
  const _ModelRow({required this.name, required this.state, required this.selected, required this.onSelected,
      required this.onRetry});
  final String name;
  final AppState state;
  final bool selected;
  final ValueChanged<bool> onSelected;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final info = modelInfo[name] ?? ModelInfo(name, '', LucideIcons.boxes);
    final m = (state.models[name] as Map).cast<String, dynamic>();
    final st = state.modelState(name);
    final ready = st == 'ready';
    final downloading = st == 'downloading';
    final size = state.modelSize(name);
    final done = ((m['bytes_done'] as num?) ?? 0).toInt();
    final onDisk = state.modelOnDisk(name);
    final progress = ((m['progress'] as num?) ?? 0).toDouble();
    final file = m['current_file'] as String?;
    final error = m['error'] as String?;
    final grey = ready ? Palette.faint : Palette.muted;
    return Container(
      key: ValueKey('models-row-$name'),
      padding: const EdgeInsets.fromLTRB(6, 8, 14, 8),
      decoration: BoxDecoration(
        color: Palette.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: st == 'error' ? Palette.error.withValues(alpha: 0.5) : Palette.border),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        Checkbox(
          key: ValueKey('models-pick-$name'),
          value: ready || selected,
          // A ready model stays ticked and grey: there is nothing to download.
          onChanged: ready || downloading ? null : (v) => onSelected(v ?? false),
        ),
        Icon(info.icon, size: 18, color: ready ? Palette.faint : Palette.accent),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text(info.title, style: Type.body.copyWith(fontWeight: FontWeight.w600, color: ready ? Palette.muted : Palette.text)),
              const SizedBox(width: 8),
              Text(formatBytes(size), style: Type.caption.copyWith(color: grey)),
            ]),
            Text(info.detail, style: Type.caption.copyWith(color: grey)),
            if (downloading) ...[
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  key: ValueKey('models-progress-$name'),
                  value: progress,
                  minHeight: 5,
                  color: Palette.accent,
                  backgroundColor: Palette.raised,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${formatBytes(done)} of ${formatBytes(size)} · ${(progress * 100).toStringAsFixed(0)}%'
                '${file == null ? '' : ' · $file'}',
                key: ValueKey('models-progress-text-$name'),
                style: Type.caption,
                overflow: TextOverflow.ellipsis,
              ),
            ] else if (st == 'error') ...[
              const SizedBox(height: 4),
              Text(error ?? 'The download failed.',
                  key: ValueKey('models-error-$name'),
                  style: Type.caption.copyWith(color: Palette.error),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ] else if (!ready && onDisk > 0) ...[
              const SizedBox(height: 2),
              Text('${formatBytes(onDisk)} already on disk; the download goes on from there.',
                  key: ValueKey('models-partial-$name'), style: Type.caption),
            ],
          ]),
        ),
        const SizedBox(width: 12),
        _StateMark(name: name, state: st, progress: progress, onRetry: onRetry),
      ]),
    );
  }
}

class _StateMark extends StatelessWidget {
  const _StateMark({required this.name, required this.state, required this.progress, required this.onRetry});
  final String name;
  final String state;
  final double progress;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case 'ready':
        return Container(
          key: ValueKey('models-ready-$name'),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          decoration: BoxDecoration(
            color: Palette.ok.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: Palette.ok.withValues(alpha: 0.5)),
          ),
          child: const Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(LucideIcons.circleCheck, size: 15, color: Palette.ok),
            SizedBox(width: 6),
            Text('Ready', style: TextStyle(fontFamily: Type.family, fontSize: 13, fontWeight: FontWeight.w600, color: Palette.ok)),
          ]),
        );
      case 'downloading':
        // A ring that fills up (determinate: it does not animate on its own).
        return Row(key: ValueKey('models-downloading-$name'), mainAxisSize: MainAxisSize.min, children: [
          SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                  value: progress, strokeWidth: 2.5, color: Palette.accent, backgroundColor: Palette.raised)),
          const SizedBox(width: 8),
          Text('${(progress * 100).toStringAsFixed(0)}%',
              style: Type.label.copyWith(color: Palette.text, fontFeatures: const [FontFeature.tabularFigures()])),
        ]);
      case 'error':
        return OutlinedButton.icon(
          key: ValueKey('models-retry-$name'),
          style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6)),
          icon: const Icon(LucideIcons.rotateCw, size: 14),
          label: const Text('Retry'),
          onPressed: onRetry,
        );
      default:
        return Text('Not downloaded', key: ValueKey('models-missing-$name'), style: Type.label);
    }
  }
}
