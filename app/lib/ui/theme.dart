import 'package:flutter/material.dart';

/// Visual language: Geist type and zinc greys in layered dark surfaces (window, panel, rows),
/// title ~17 pt, body ~14 pt, captions ~12–13 pt, 8 px corners and a periwinkle accent.
abstract final class Palette {
  static const window = Color(0xFF131315);
  static const panel = Color(0xFF1B1B1E);
  static const surface = Color(0xFF18181B); // rows
  static const raised = Color(0xFF232327); // inputs, menus, chips
  static const border = Color(0xFF2B2B30);
  static const text = Color(0xFFEDEDEF);
  static const muted = Color(0xFFA1A1AA);
  static const faint = Color(0xFF6E6E78);
  static const accent = Color(0xFF8C8CF7);
  static const onAccent = Color(0xFF101014);
  static const review = Color(0xFFF2B35B);
  static const ok = Color(0xFF4ADE80);
  static const error = Color(0xFFF87171);
}

/// Every style names its family: widgets such as DropdownButton and button themes replace
/// the inherited style instead of merging with it.
abstract final class Type {
  static const family = 'Geist';
  static const _fallback = ['PingFang TC', 'Hiragino Sans', 'Arial Unicode MS'];
  static const title = TextStyle(fontFamily: family, fontFamilyFallback: _fallback, fontSize: 17, fontWeight: FontWeight.w600, letterSpacing: -0.2, color: Palette.text);
  static const body = TextStyle(fontFamily: family, fontFamilyFallback: _fallback, fontSize: 14, height: 20 / 14, color: Palette.text);
  static const bodyMuted = TextStyle(fontFamily: family, fontFamilyFallback: _fallback, fontSize: 14, height: 20 / 14, color: Palette.muted);
  static const label = TextStyle(fontFamily: family, fontFamilyFallback: _fallback, fontSize: 13, fontWeight: FontWeight.w500, color: Palette.muted);
  static const caption = TextStyle(fontFamily: family, fontFamilyFallback: _fallback, fontSize: 12, color: Palette.muted);
  static const columnHeader =
      TextStyle(fontFamily: family, fontSize: 12, fontWeight: FontWeight.w500, letterSpacing: 0.2, color: Palette.faint);
  static const mono = TextStyle(fontFamily: 'GeistMono', fontSize: 12, color: Palette.muted);
}

const _radius = 8.0;

/// Colour for enabled buttons; disabled ones fade to the faint grey.
WidgetStateProperty<Color> _whenEnabled(Color color) =>
    WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.disabled) ? const Color(0xFF52525B) : color);

ThemeData buildTheme({String fontFamily = 'Geist'}) {
  final scheme = ColorScheme.fromSeed(seedColor: Palette.accent, brightness: Brightness.dark).copyWith(
    primary: Palette.accent,
    onPrimary: Palette.onAccent,
    secondary: const Color(0xFF3A3A44),
    onSecondary: Palette.text,
    surface: Palette.panel,
    onSurface: Palette.text,
    onSurfaceVariant: Palette.muted,
    surfaceContainerLowest: Palette.window,
    surfaceContainerLow: Palette.surface,
    surfaceContainer: Palette.panel,
    surfaceContainerHigh: Palette.raised,
    surfaceContainerHighest: const Color(0xFF2A2A2F),
    outline: const Color(0xFF3F3F46),
    outlineVariant: Palette.border,
    error: Palette.error,
  );
  // Buttons share the 8 px corner of inputs and menus instead of pill shapes.
  final buttonShape = WidgetStatePropertyAll<OutlinedBorder>(
      RoundedRectangleBorder(borderRadius: BorderRadius.circular(_radius)));
  const buttonText = WidgetStatePropertyAll(TextStyle(fontFamily: Type.family, fontSize: 14, fontWeight: FontWeight.w600));
  const buttonPadding = WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 18, vertical: 10));
  // CJK file names fall back to the system's CJK fonts.
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, fontFamily: fontFamily,
      fontFamilyFallback: const ['PingFang TC', 'Hiragino Sans', 'Arial Unicode MS']);
  return base.copyWith(
    scaffoldBackgroundColor: Palette.window,
    visualDensity: VisualDensity.compact,
    textTheme: base.textTheme
        .copyWith(
          titleLarge: Type.title,
          bodyMedium: Type.body,
          bodySmall: Type.caption,
          labelMedium: Type.label,
          labelLarge: const TextStyle(fontFamily: Type.family, fontSize: 14, fontWeight: FontWeight.w600),
        )
        .apply(fontFamily: fontFamily),
    dividerTheme: const DividerThemeData(color: Palette.border, thickness: 1, space: 1),
    iconTheme: const IconThemeData(color: Palette.muted, size: 18),
    filledButtonTheme: FilledButtonThemeData(
      style: ButtonStyle(shape: buttonShape, textStyle: buttonText, padding: buttonPadding),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: buttonText,
        padding: buttonPadding,
        foregroundColor: _whenEnabled(Palette.text),
        side: WidgetStateProperty.resolveWith((s) => BorderSide(
            color: s.contains(WidgetState.disabled) ? Palette.border : const Color(0xFF3F3F46))),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(shape: buttonShape, textStyle: buttonText, padding: buttonPadding,
          foregroundColor: _whenEnabled(Palette.muted)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: Palette.raised,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      hintStyle: const TextStyle(color: Palette.faint),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(_radius), borderSide: const BorderSide(color: Palette.border)),
      enabledBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(_radius), borderSide: const BorderSide(color: Palette.border)),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(_radius), borderSide: const BorderSide(color: Palette.accent, width: 1.5)),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: Palette.raised,
      surfaceTintColor: Colors.transparent,
      textStyle: Type.body,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10), side: const BorderSide(color: Palette.border)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Palette.panel,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: Type.title.copyWith(fontFamily: fontFamily),
      contentTextStyle: Type.body.copyWith(fontFamily: fontFamily),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14), side: const BorderSide(color: Palette.border)),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: Palette.raised,
      side: const BorderSide(color: Palette.border),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      labelStyle: Type.label.copyWith(fontFamily: fontFamily),
      padding: const EdgeInsets.symmetric(horizontal: 6),
    ),
    checkboxTheme: CheckboxThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
      side: const BorderSide(color: Color(0xFF52525B), width: 1.5),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: const Color(0xFF2E2E34), borderRadius: BorderRadius.circular(6)),
      textStyle: Type.caption.copyWith(color: Palette.text, fontFamily: fontFamily),
    ),
    snackBarTheme: const SnackBarThemeData(backgroundColor: Palette.raised, contentTextStyle: Type.body),
    listTileTheme: const ListTileThemeData(dense: true, titleTextStyle: Type.body, subtitleTextStyle: Type.caption),
  );
}

/// Rows the user should check (low or no confidence): a thin amber bar and a faint tint.
const reviewHighlight = Color(0x14F2B35B);
const reviewText = Palette.review;
