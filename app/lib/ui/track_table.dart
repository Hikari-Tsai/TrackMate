import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../app_state.dart';
import '../models.dart';
import 'pickers.dart';
import 'theme.dart';

const _confidenceLabel = {
  Confidence.high: 'High',
  Confidence.medium: 'Medium',
  Confidence.low: 'Low',
  Confidence.none: 'None',
};
const _confidenceColor = {
  Confidence.high: Color(0xFF4ADE80),
  Confidence.medium: Color(0xFF60A5FA),
  Confidence.low: Palette.review,
  Confidence.none: Palette.faint,
};
// How a track was recognised, in plain words (engine stages A–D, see recognitionHelp).
const _stageLabel = {
  'A': 'Known track name', 'A+C': 'Known name, refined by AI', 'A+D': 'Known name, confirmed by sound',
  'B': 'Spelling corrected', 'C': 'AI read the name', 'C+D': 'AI read the name and checked the sound',
  'D': 'Recognised by its sound', 'none': 'Not recognised',
};

/// Shown on the Confidence column and in the header.
const recognitionHelp = '''How tracks are recognised, in this order:
1. Known track names: a list of common names and abbreviations (Kick In, BV, OH, 鋼琴…)
2. Spelling: catches typos (Snaer -> Snare)
3. AI name reading: understands names it has never seen, also Chinese and Japanese
4. Sound: listens to the audio when the name says nothing (Audio 3, Untitled)

High: known name. Medium: spelling fix, or AI sure enough. Low: please check.''';
// What the percentage measures for each stage.
const _scoreMeaning = {
  'A': 'name match', 'A+C': 'name similarity', 'A+D': 'name match', 'B': 'spelling match',
  'C': 'name similarity', 'C+D': 'name similarity', 'D': 'sound match',
};
const _stereoLabel = {
  'mono_file': 'Mono', 'silent': 'Silent', 'fake_stereo': 'Fake stereo', 'hard_left': 'Left only',
  'hard_right': 'Right only', 'delayed_mono': 'Delayed mono', 'true_stereo': 'Stereo', 'multichannel': 'Multichannel',
};

// Column widths shared by the header and the rows.
const _wCategory = 176.0;
const _wColour = 52.0;
const _wConfidence = 150.0;
const _wMono = 150.0;
const _wEnd = 36.0;

class TrackHeader extends StatelessWidget {
  const TrackHeader({super.key});

  @override
  Widget build(BuildContext context) {
    Widget cell(String t, {int flex = 0, double? width}) => flex > 0
        ? Expanded(flex: flex, child: Text(t, style: Type.columnHeader))
        : SizedBox(width: width, child: Text(t, style: Type.columnHeader));
    return Padding(
      padding: const EdgeInsets.fromLTRB(28, 6, 28, 8),
      child: Row(children: [
        cell('Original file', flex: 3),
        cell('New name', flex: 3),
        const SizedBox(width: 12),
        cell('Category', width: _wCategory),
        const SizedBox(width: 14),
        cell('Colour', width: _wColour),
        SizedBox(
          width: _wConfidence,
          child: Tooltip(
            message: recognitionHelp,
            child: Row(children: [
              Text('Confidence', style: Type.columnHeader),
              SizedBox(width: 4),
              Icon(LucideIcons.info, size: 12, color: Palette.faint),
            ]),
          ),
        ),
        cell('To mono', width: _wMono),
        const SizedBox(width: _wEnd),
      ]),
    );
  }
}

class TrackRowView extends StatefulWidget {
  const TrackRowView({super.key, required this.row, required this.state});
  final TrackRow row;
  final AppState state;

  @override
  State<TrackRowView> createState() => _TrackRowViewState();
}

class _TrackRowViewState extends State<TrackRowView> {
  // Shows the final name, including the running number of duplicates.
  late final TextEditingController _name = TextEditingController(text: widget.state.finalName(widget.row));

  @override
  void didUpdateWidget(covariant TrackRowView old) {
    super.didUpdateWidget(old);
    final name = widget.state.finalName(widget.row);
    if (_name.text != name) _name.text = name;
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _openCandidates(BuildContext context) async {
    final row = widget.row;
    final catalog = widget.state.catalog!;
    final width = (context.findRenderObject() as RenderBox).size.width;
    PopupMenuItem<String> action(String key, String value, IconData icon, String label) => PopupMenuItem(
          key: ValueKey(key),
          value: value,
          height: 38,
          child: Row(children: [
            Icon(icon, size: 15, color: Palette.muted),
            const SizedBox(width: 10),
            Flexible(child: Text(label, overflow: TextOverflow.ellipsis)),
          ]),
        );
    final choice = await showMenuBelow<String>(
      context,
      maxWidth: width.clamp(260, 420),
      [
        for (final c in row.candidates)
          PopupMenuItem(
            key: ValueKey('candidate-${c.instrument}'),
            value: c.instrument,
            height: 38,
            child: Row(children: [
              _Dot(Color(catalog.color(catalog.category(c.category).colorIndex))),
              const SizedBox(width: 10),
              Expanded(
                child: Text(c.label,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontWeight: c.instrument == row.instrument ? FontWeight.w600 : FontWeight.w400)),
              ),
              if (c.instrument == row.instrument) ...[
                const Icon(LucideIcons.check, size: 14, color: Palette.accent),
                const SizedBox(width: 8),
              ],
              SizedBox(width: 40, child: Text(percent(c.score), textAlign: TextAlign.right, style: Type.mono)),
            ]),
          ),
        const PopupMenuDivider(height: 9),
        action('menu-type', '__type', LucideIcons.pencil, 'Type a name…'),
        action('menu-search', '__search', LucideIcons.search, 'Search all instruments…'),
        action('menu-keep', '__keep', LucideIcons.undo2, 'Keep original name'),
      ],
    );
    if (!mounted || choice == null) return;
    switch (choice) {
      case '__keep':
        widget.state.keepOriginalName(row);
      case '__type':
        final name = await showNameEntry(this.context, row.name);
        if (name != null) widget.state.rename(row, name);
      case '__search':
        final id = await showInstrumentSearch(this.context, catalog);
        if (id != null) widget.state.chooseInstrument(row, id);
      default:
        widget.state.chooseInstrument(row, choice);
    }
  }

  @override
  Widget build(BuildContext context) {
    final row = widget.row;
    final state = widget.state;
    final catalog = state.catalog!;
    final applied = row.applyResult;
    final appliedOk = applied != null && applied['name_ok'] == true && applied['folder_ok'] == true &&
        applied['color_ok'] == true && (applied['errors'] as List).isEmpty;
    final review = row.needsReview;
    return Container(
      key: ValueKey('row-${row.originalName}'),
      decoration: BoxDecoration(
        color: review ? Color.alphaBlend(reviewHighlight, Palette.surface) : Palette.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: review ? Palette.review.withValues(alpha: 0.35) : Palette.border),
      ),
      padding: const EdgeInsets.fromLTRB(16, 6, 6, 6),
      child: Row(children: [
        Expanded(
          flex: 3,
          child: Row(children: [
            Icon(LucideIcons.fileAudio, size: 15, color: review ? Palette.review : Palette.faint),
            const SizedBox(width: 10),
            Expanded(
              child: Tooltip(
                message: row.file,
                child: Text(row.originalName, overflow: TextOverflow.ellipsis, style: Type.bodyMuted),
              ),
            ),
          ]),
        ),
        Expanded(
          flex: 3,
          child: Builder(
            builder: (ctx) => SizedBox(
              height: 36,
              child: TextField(
                key: ValueKey('name-${row.originalName}'),
                controller: _name,
                style: Type.body.copyWith(fontWeight: FontWeight.w500),
                decoration: InputDecoration(
                  suffixIcon: IconButton(
                    key: ValueKey('candidates-${row.originalName}'),
                    tooltip: 'Candidates',
                    icon: const Icon(LucideIcons.chevronDown, size: 16),
                    onPressed: () => _openCandidates(ctx),
                  ),
                ),
                onSubmitted: (v) => state.rename(row, v),
                onTapOutside: (_) => state.rename(row, _name.text),
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        SizedBox(width: _wCategory, child: _CategoryButton(row: row, state: state)),
        const SizedBox(width: 14),
        SizedBox(
          width: _wColour,
          child: Align(
            alignment: Alignment.centerLeft,
            child: Tooltip(
              message: row.colorOverridden ? 'Custom colour #${row.colorIndex}' : 'Category colour #${row.colorIndex}',
              child: InkWell(
                key: ValueKey('color-${row.originalName}'),
                borderRadius: BorderRadius.circular(6),
                onTap: () async {
                  final idx = await showPalettePicker(context, catalog, row.colorIndex);
                  if (idx != null) state.setColor(row, idx);
                },
                child: Container(
                  width: 28,
                  height: 20,
                  decoration: BoxDecoration(
                    color: Color(catalog.color(row.colorIndex)),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
                  ),
                ),
              ),
            ),
          ),
        ),
        SizedBox(width: _wConfidence, child: _confidence(row)),
        SizedBox(
          width: _wMono,
          child: Row(children: [
            SizedBox(
              width: 32,
              child: Checkbox(
                key: ValueKey('mono-${row.originalName}'),
                value: row.mono,
                onChanged: row.stereoType == 'mono_file' ? null : (v) => state.setMono(row, v ?? false),
              ),
            ),
            const SizedBox(width: 4),
            Flexible(
              child: Tooltip(
                message: row.mono ? 'Convert to mono before import (${row.stereoAction})' : 'Keep the channels as they are',
                child: Text(_stereoLabel[row.stereoType] ?? row.stereoType, overflow: TextOverflow.ellipsis, style: Type.caption),
              ),
            ),
          ]),
        ),
        SizedBox(
          width: _wEnd,
          child: applied != null
              ? Tooltip(
                  message: appliedOk ? 'Imported as ${applied['pt_name']}' : 'Problem: ${applied['errors']}',
                  child: Icon(appliedOk ? LucideIcons.circleCheck : LucideIcons.circleAlert,
                      size: 18, color: appliedOk ? Palette.ok : Palette.error),
                )
              : IconButton(
                  tooltip: 'Remove',
                  iconSize: 16,
                  icon: const Icon(LucideIcons.x, color: Palette.faint),
                  onPressed: () => state.remove(row),
                ),
        ),
      ]),
    );
  }

  Widget _confidence(TrackRow row) {
    if (row.audioPending) {
      return const Row(children: [
        SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 1.5, color: Palette.accent)),
        SizedBox(width: 8),
        Text('Listening…', style: Type.caption),
      ]);
    }
    final color = row.edited ? Palette.accent : _confidenceColor[row.confidence]!;
    final score = row.edited ? null : row.score;
    final stage = _stageLabel[row.stage] ?? row.stage;
    return Tooltip(
      message: score == null ? stage : '$stage · ${percent(score)} ${_scoreMeaning[row.stage] ?? 'score'}',
      child: Row(children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(6)),
          child: Text(row.edited ? 'Edited' : _confidenceLabel[row.confidence]!,
              style: Type.caption.copyWith(color: color, fontWeight: FontWeight.w500)),
        ),
        const SizedBox(width: 8),
        if (score != null)
          Text(percent(score), key: ValueKey('score-${row.originalName}'), style: Type.mono.copyWith(color: Palette.text))
        else
          Flexible(child: Text(stage, overflow: TextOverflow.ellipsis, style: Type.caption)),
      ]),
    );
  }
}

/// Category picker. A popup menu below the button rather than DropdownButton, whose menu opens
/// around the selected item and grows up and down at the same time.
class _CategoryButton extends StatelessWidget {
  const _CategoryButton({required this.row, required this.state});
  final TrackRow row;
  final AppState state;

  Future<void> _open(BuildContext context) async {
    final catalog = state.catalog!;
    final choice = await showMenuBelow<String>(
      context,
      maxWidth: 240,
      [
        for (final c in catalog.categories)
          PopupMenuItem(
            key: ValueKey('category-item-${c.id}'),
            value: c.id,
            height: 34,
            child: Row(children: [
              _Dot(Color(catalog.color(c.colorIndex))),
              const SizedBox(width: 10),
              Expanded(
                child: Text(c.label,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontWeight: c.id == row.category ? FontWeight.w600 : FontWeight.w400)),
              ),
              if (c.id == row.category) const Icon(LucideIcons.check, size: 14, color: Palette.accent),
            ]),
          ),
      ],
    );
    if (choice != null && choice != row.category) state.setCategory(row, choice);
  }

  @override
  Widget build(BuildContext context) {
    final catalog = state.catalog!;
    final cat = catalog.category(row.category);
    return Builder(
      builder: (ctx) => InkWell(
        key: ValueKey('category-${row.originalName}'),
        borderRadius: BorderRadius.circular(8),
        onTap: () => _open(ctx),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(children: [
            _Dot(Color(catalog.color(cat.colorIndex))),
            const SizedBox(width: 8),
            Expanded(child: Text(cat.label, overflow: TextOverflow.ellipsis, style: Type.body)),
            const Icon(LucideIcons.chevronDown, size: 14, color: Palette.muted),
          ]),
        ),
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot(this.color);
  final Color color;

  @override
  Widget build(BuildContext context) =>
      Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
}
