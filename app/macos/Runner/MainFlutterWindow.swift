import Cocoa
import FlutterMacOS

/// Accepts files dragged from Finder anywhere in the window. The Flutter view is a subview, so
/// AppKit walks up from it to this view, which is registered for file URLs.
class DropContainerView: NSView {
  var onDrop: (([String]) -> Void)?
  var onHover: ((Bool) -> Void)?

  override init(frame: NSRect) {
    super.init(frame: frame)
    registerForDraggedTypes([.fileURL])
  }

  required init?(coder: NSCoder) {
    fatalError("init(coder:) is not used")
  }

  private func fileURLs(_ info: NSDraggingInfo) -> [URL] {
    let options: [NSPasteboard.ReadingOptionKey: Any] = [.urlReadingFileURLsOnly: true]
    return info.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: options) as? [URL] ?? []
  }

  override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
    let accept = !fileURLs(sender).isEmpty
    onHover?(accept)
    return accept ? .copy : []
  }

  override func draggingExited(_ sender: NSDraggingInfo?) {
    onHover?(false)
  }

  override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
    onHover?(false)
    let urls = fileURLs(sender)
    if urls.isEmpty { return false }
    onDrop?(urls.map { $0.path })
    return true
  }
}

/// Root controller: the drop container with the Flutter view inside, and the
/// "stem_import/native" channel (pickFiles from Dart; filesDropped / dragHover to Dart).
class RootViewController: NSViewController {
  let flutter = FlutterViewController()
  private var channel: FlutterMethodChannel!

  override func loadView() {
    let container = DropContainerView(frame: NSRect(x: 0, y: 0, width: 1320, height: 820))
    addChild(flutter)
    flutter.view.frame = container.bounds
    flutter.view.autoresizingMask = [.width, .height]
    container.addSubview(flutter.view)
    view = container

    channel = FlutterMethodChannel(name: "stem_import/native", binaryMessenger: flutter.engine.binaryMessenger)
    container.onDrop = { [weak self] paths in self?.channel.invokeMethod("filesDropped", arguments: paths) }
    container.onHover = { [weak self] on in self?.channel.invokeMethod("dragHover", arguments: on) }
    channel.setMethodCallHandler { [weak self] call, result in
      switch call.method {
      case "pickFiles":
        self?.pickFiles(result)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func pickFiles(_ result: @escaping FlutterResult) {
    let panel = NSOpenPanel()
    panel.allowsMultipleSelection = true
    panel.canChooseDirectories = true
    panel.canChooseFiles = true
    panel.message = "Choose stems or folders"
    panel.begin { response in
      result(response == .OK ? panel.urls.map { $0.path } : [])
    }
  }
}

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let root = RootViewController()
    self.contentViewController = root
    self.setContentSize(NSSize(width: 1320, height: 820))
    self.minSize = NSSize(width: 1000, height: 600)
    self.title = "TrackMate"
    self.appearance = NSAppearance(named: .darkAqua)  // dark title bar to match the app
    self.center()

    RegisterGeneratedPlugins(registry: root.flutter)

    super.awakeFromNib()
  }
}
