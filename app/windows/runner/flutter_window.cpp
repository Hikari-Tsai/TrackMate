#include "flutter_window.h"

#include <flutter/standard_method_codec.h>
#include <shobjidl.h>

#include <optional>
#include <string>

#include "flutter/generated_plugin_registrant.h"
#include "utils.h"

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  // Files dropped on the window and the open dialog, as macos/Runner/MainFlutterWindow.swift
  // provides on macOS. Windows does not report drag hover here, so "dragHover" is not sent.
  channel_ = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "stem_import/native",
      &flutter::StandardMethodCodec::GetInstance());
  channel_->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& call,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
        if (call.method_name() == "pickFiles") {
          result->Success(flutter::EncodableValue(PickFiles()));
        } else {
          result->NotImplemented();
        }
      });
  DragAcceptFiles(GetHandle(), TRUE);

  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    this->Show();
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  channel_ = nullptr;
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
    case WM_DROPFILES:
      HandleDrop(reinterpret_cast<HDROP>(wparam));
      return 0;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}

void FlutterWindow::HandleDrop(HDROP drop) {
  flutter::EncodableList paths;
  const UINT count = DragQueryFileW(drop, 0xFFFFFFFF, nullptr, 0);
  for (UINT i = 0; i < count; ++i) {
    const UINT length = DragQueryFileW(drop, i, nullptr, 0);
    std::wstring path(length + 1, L'\0');
    DragQueryFileW(drop, i, path.data(), length + 1);
    path.resize(length);
    paths.push_back(flutter::EncodableValue(Utf8FromUtf16(path.c_str())));
  }
  DragFinish(drop);
  if (channel_ && !paths.empty()) {
    channel_->InvokeMethod("filesDropped", std::make_unique<flutter::EncodableValue>(paths));
  }
}

flutter::EncodableList FlutterWindow::PickFiles() {
  flutter::EncodableList paths;
  IFileOpenDialog* dialog = nullptr;
  if (FAILED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER,
                              IID_PPV_ARGS(&dialog)))) {
    return paths;
  }
  DWORD options = 0;
  dialog->GetOptions(&options);
  dialog->SetOptions(options | FOS_ALLOWMULTISELECT | FOS_FORCEFILESYSTEM | FOS_FILEMUSTEXIST);
  const COMDLG_FILTERSPEC types[] = {
      {L"Audio files", L"*.wav;*.wave;*.aif;*.aiff;*.mp3;*.flac;*.m4a;*.ogg;*.caf"},
      {L"All files", L"*.*"},
  };
  dialog->SetFileTypes(2, types);
  dialog->SetTitle(L"Choose stems");
  if (SUCCEEDED(dialog->Show(GetHandle()))) {
    IShellItemArray* items = nullptr;
    if (SUCCEEDED(dialog->GetResults(&items))) {
      DWORD n = 0;
      items->GetCount(&n);
      for (DWORD i = 0; i < n; ++i) {
        IShellItem* item = nullptr;
        if (SUCCEEDED(items->GetItemAt(i, &item))) {
          PWSTR path = nullptr;
          if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
            paths.push_back(flutter::EncodableValue(Utf8FromUtf16(path)));
            CoTaskMemFree(path);
          }
          item->Release();
        }
      }
      items->Release();
    }
  }
  dialog->Release();
  return paths;
}
