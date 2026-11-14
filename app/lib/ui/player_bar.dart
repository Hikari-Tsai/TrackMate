import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../app_state.dart';
import '../player.dart';
import 'theme.dart';

/// Under the list while a stem is being listened to: the file, play/pause, a seek bar with
/// the time, and a close button. Position ticks only redraw the slider and the clock.
class PlayerBar extends StatelessWidget {
  const PlayerBar({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final a = state.audition;
    return ListenableBuilder(
      listenable: a,
      builder: (context, _) {
        final row = a.track;
        if (row == null) return const SizedBox.shrink();
        final newName = state.finalName(row);
        return Container(
          key: const ValueKey('player-bar'),
          decoration: const BoxDecoration(
            color: Palette.surface,
            border: Border(top: BorderSide(color: Palette.border)),
          ),
          padding: const EdgeInsets.fromLTRB(20, 8, 10, 8),
          child: Row(children: [
            const Icon(LucideIcons.headphones, size: 16, color: Palette.accent),
            const SizedBox(width: 10),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 300),
              child: Tooltip(
                message: row.file,
                child: Text.rich(
                  TextSpan(children: [
                    TextSpan(text: row.originalName, style: Type.body.copyWith(fontWeight: FontWeight.w500)),
                    if (newName != row.originalName) TextSpan(text: '  →  $newName', style: Type.bodyMuted),
                  ]),
                  key: const ValueKey('player-title'),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                ),
              ),
            ),
            const SizedBox(width: 14),
            IconButton(
              key: const ValueKey('player-toggle'),
              tooltip: a.playing ? 'Pause' : 'Play',
              iconSize: 18,
              color: Palette.text,
              icon: Icon(a.playing ? LucideIcons.pause : LucideIcons.play),
              onPressed: a.error == null ? a.toggle : null,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: a.error != null
                  ? Row(children: [
                      const Icon(LucideIcons.circleAlert, size: 15, color: Palette.error),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(a.error!,
                            key: const ValueKey('player-error'),
                            style: Type.caption.copyWith(color: Palette.error),
                            overflow: TextOverflow.ellipsis),
                      ),
                    ])
                  : _Seek(audition: a),
            ),
            const SizedBox(width: 6),
            IconButton(
              key: const ValueKey('player-close'),
              tooltip: 'Stop listening',
              iconSize: 16,
              icon: const Icon(LucideIcons.x, color: Palette.faint),
              onPressed: a.close,
            ),
          ]),
        );
      },
    );
  }
}

class _Seek extends StatelessWidget {
  const _Seek({required this.audition});
  final Audition audition;

  @override
  Widget build(BuildContext context) {
    final total = audition.duration;
    return ValueListenableBuilder<Duration>(
      valueListenable: audition.position,
      builder: (context, pos, _) {
        final max = total == null || total == Duration.zero ? 1.0 : total.inMilliseconds.toDouble();
        final value = total == null ? 0.0 : pos.inMilliseconds.toDouble().clamp(0.0, max);
        return Row(children: [
          Expanded(
            child: SliderTheme(
              data: SliderThemeData(
                trackHeight: 3,
                activeTrackColor: Palette.accent,
                inactiveTrackColor: Palette.border,
                thumbColor: Palette.accent,
                overlayColor: Palette.accent.withValues(alpha: 0.15),
                thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
                overlayShape: const RoundSliderOverlayShape(overlayRadius: 12),
              ),
              child: Slider(
                key: const ValueKey('player-seek'),
                value: value,
                max: max,
                onChanged: total == null ? null : (v) => audition.position.value = Duration(milliseconds: v.round()),
                onChangeEnd: total == null ? null : (v) => audition.seek(Duration(milliseconds: v.round())),
              ),
            ),
          ),
          const SizedBox(width: 10),
          Text(
            '${clock(pos)} / ${total == null ? '–:––' : clock(total)}',
            key: const ValueKey('player-clock'),
            style: Type.mono.copyWith(color: Palette.text),
          ),
        ]);
      },
    );
  }
}
