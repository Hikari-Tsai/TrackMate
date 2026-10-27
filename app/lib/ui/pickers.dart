import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../models.dart';

/// Popup menu that opens right below [anchor] and grows downwards. When the items do not fit
/// below, the menu gets the height that is left and scrolls, instead of being pushed up over the
/// button. Only when less than [minBelow] is left (button at the bottom of the window) does it
/// open above.
Future<T?> showMenuBelow<T>(BuildContext anchor, List<PopupMenuEntry<T>> items,
    {double? minWidth, double maxWidth = 420, double minBelow = 180}) {
  final box = anchor.findRenderObject() as RenderBox;
  final screen = MediaQuery.sizeOf(anchor);
  final topLeft = box.localToGlobal(Offset.zero);
  final below = screen.height - (topLeft.dy + box.size.height) - 12;
  final openBelow = below >= minBelow;
  final y = openBelow ? topLeft.dy + box.size.height + 4 : topLeft.dy - 4;
  return showMenu<T>(
    context: anchor,
    position: openBelow
        ? RelativeRect.fromLTRB(topLeft.dx, y, screen.width - topLeft.dx - box.size.width, 0)
        : RelativeRect.fromLTRB(topLeft.dx, 0, screen.width - topLeft.dx - box.size.width, screen.height - y),
    constraints: BoxConstraints(
      minWidth: minWidth ?? box.size.width,
      maxWidth: maxWidth,
      maxHeight: openBelow ? below : topLeft.dy - 16,
    ),
    items: items,
  );
}

/// Pro Tools track palette (69 colours, 3 rows of 23). Returns the 1-based index.
Future<int?> showPalettePicker(BuildContext context, Catalog catalog, int current) {
  final scheme = Theme.of(context).colorScheme;
  return showDialog<int>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Choose a colour (Pro Tools palette)'),
      content: SizedBox(
        width: 23 * 26,
        child: Wrap(
          spacing: 2,
          runSpacing: 2,
          children: [
            for (var i = 1; i <= catalog.palette.length; i++)
              Tooltip(
                message: '#$i',
                child: InkWell(
                  key: ValueKey('swatch-$i'),
                  onTap: () => Navigator.pop(ctx, i),
                  child: Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      color: Color(catalog.color(i)),
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                          color: i == current ? scheme.onSurface : Colors.white.withValues(alpha: 0.08), width: i == current ? 2.5 : 1),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel'))],
    ),
  );
}

/// "Type a name…": free text for the track name. Returns null when cancelled or empty.
Future<String?> showNameEntry(BuildContext context, String current) {
  return showDialog<String>(context: context, builder: (_) => _NameEntry(current: current));
}

/// Owns its text controller, so the controller lives until the dialog's closing animation
/// has finished (disposing it when the future completes is too early).
class _NameEntry extends StatefulWidget {
  const _NameEntry({required this.current});
  final String current;

  @override
  State<_NameEntry> createState() => _NameEntryState();
}

class _NameEntryState extends State<_NameEntry> {
  late final TextEditingController _controller = TextEditingController(text: widget.current)
    ..selection = TextSelection(baseOffset: 0, extentOffset: widget.current.length);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final v = _controller.text.trim();
    Navigator.pop(context, v.isEmpty ? null : v);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Type a track name'),
      content: SizedBox(
        width: 420,
        child: TextField(
          key: const ValueKey('name-entry-field'),
          controller: _controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'e.g. Kick In 2', helperText: 'Used as the Pro Tools track name'),
          onSubmitted: (_) => _submit(),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(key: const ValueKey('name-entry-ok'), onPressed: _submit, child: const Text('Use name')),
      ],
    );
  }
}

/// "Search all instruments…": filter by instrument label, id or category name.
Future<String?> showInstrumentSearch(BuildContext context, Catalog catalog) {
  return showDialog<String>(
    context: context,
    builder: (ctx) => _InstrumentSearch(catalog: catalog),
  );
}

class _InstrumentSearch extends StatefulWidget {
  const _InstrumentSearch({required this.catalog});
  final Catalog catalog;

  @override
  State<_InstrumentSearch> createState() => _InstrumentSearchState();
}

class _InstrumentSearchState extends State<_InstrumentSearch> {
  String query = '';

  @override
  Widget build(BuildContext context) {
    final q = query.toLowerCase().trim();
    final items = widget.catalog.instruments.where((i) {
      if (q.isEmpty) return true;
      final cat = widget.catalog.category(i.category);
      return i.label.toLowerCase().contains(q) || i.id.contains(q) || cat.name.toLowerCase().contains(q);
    }).toList();
    return AlertDialog(
      title: const Text('Search all instruments'),
      content: SizedBox(
        width: 420,
        height: 460,
        child: Column(children: [
          TextField(
            key: const ValueKey('instrument-search-field'),
            autofocus: true,
            decoration: const InputDecoration(prefixIcon: Icon(LucideIcons.search, size: 16), hintText: 'Instrument or category, e.g. piano, drums'),
            onChanged: (v) => setState(() => query = v),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (_, k) {
                final i = items[k];
                final cat = widget.catalog.category(i.category);
                return ListTile(
                  dense: true,
                  leading: CircleAvatar(radius: 6, backgroundColor: Color(widget.catalog.color(cat.colorIndex))),
                  title: Text(i.label),
                  subtitle: Text(cat.label),
                  onTap: () => Navigator.pop(context, i.id),
                );
              },
            ),
          ),
        ]),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel'))],
    );
  }
}
