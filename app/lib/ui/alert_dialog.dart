import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../alerts.dart';
import 'theme.dart';

/// Shows [alert]; returns true when the user chose its action (Try again / Restart engine).
Future<bool> showAlert(BuildContext context, AppAlert alert) async {
  final res = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      key: ValueKey('alert-${alert.code}'),
      icon: const Icon(LucideIcons.triangleAlert, color: Palette.review, size: 28),
      title: Text(alert.title),
      content: SizedBox(
        width: 440,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(alert.message, style: Type.body),
          if (alert.details.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              constraints: const BoxConstraints(maxHeight: 160),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: Palette.surface, borderRadius: BorderRadius.circular(8)),
              child: SingleChildScrollView(
                child: SelectableText(alert.details.join('\n'), style: Type.mono.copyWith(color: Palette.text)),
              ),
            ),
          ],
        ]),
      ),
      actions: [
        TextButton(
          key: const ValueKey('alert-close'),
          onPressed: () => Navigator.pop(ctx, false),
          child: Text(alert.action == AlertAction.none ? 'OK' : 'Cancel'),
        ),
        if (alert.action != AlertAction.none)
          FilledButton(
            key: const ValueKey('alert-action'),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(alert.action == AlertAction.tryAgain ? 'Try again' : 'Restart engine'),
          ),
      ],
    ),
  );
  return res ?? false;
}
