import 'engine/engine_api.dart';

/// What the user can do from an alert besides closing it.
enum AlertAction { none, tryAgain, restartEngine }

/// A problem the user has to know about, shown as a dialog.
class AppAlert {
  const AppAlert(this.title, this.message, {this.details = const [], this.action = AlertAction.none, this.code = ''});

  final String title;
  final String message;
  final List<String> details; // e.g. the files that were not found
  final AlertAction action;
  final String code; // engine error code, for tests and logs

  static const supportedFormats = 'WAV, AIFF, MP3, FLAC, M4A, OGG or CAF';

  static const noAudioFiles = AppAlert(
    'No audio files found',
    'TrackMate imports $supportedFormats files. Folders are searched for them.',
    code: 'no_audio_files',
  );

  /// Turns an engine error into words. [doing] names the step, e.g. "apply".
  factory AppAlert.fromError(Object error, {String doing = ''}) {
    if (error is! EngineException) {
      return AppAlert('Something went wrong', '$error', code: 'unexpected');
    }
    switch (error.code) {
      case 'pro_tools_not_running':
        return const AppAlert('Pro Tools is not running', 'Open Pro Tools and a session, then try again.',
            action: AlertAction.tryAgain, code: 'pro_tools_not_running');
      case 'no_session':
        return const AppAlert('No session is open in Pro Tools',
            'Open or create a session in Pro Tools, then try again.',
            action: AlertAction.tryAgain, code: 'no_session');
      case 'pro_tools_not_responding':
        return const AppAlert('Pro Tools is not responding',
            'Pro Tools may be busy or showing a dialog. Close any open dialogs in Pro Tools, then try again.',
            action: AlertAction.tryAgain, code: 'pro_tools_not_responding');
      case 'pro_tools_lost':
        return AppAlert('Pro Tools stopped during the import',
            'Some folders or tracks may already be in the session. Check the session in Pro Tools before you apply again.',
            details: [error.message], code: 'pro_tools_lost');
      case 'missing_files':
        return AppAlert('Files not found',
            'These files were moved, renamed or deleted. Remove them from the list or add them again.',
            details: error.files, code: 'missing_files');
      case 'engine_unreachable':
        return const AppAlert('The TrackMate engine stopped',
            'Recognition and import need the engine. Restart it to continue; your list stays as it is.',
            action: AlertAction.restartEngine, code: 'engine_unreachable');
      default:
        return AppAlert(doing.isEmpty ? 'Something went wrong' : 'Could not $doing', error.message,
            code: error.code.isEmpty ? 'http_${error.status}' : error.code);
    }
  }
}
