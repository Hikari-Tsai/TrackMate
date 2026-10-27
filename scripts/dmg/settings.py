# dmgbuild settings for the macOS installer: TrackMate on the left, an Applications shortcut on
# the right, and a background with an arrow between them (make_background.py).
# Usage: dmgbuild -s scripts/dmg/settings.py -D app=<TrackMate.app> -D background=scripts/dmg/background.png \
#          TrackMate <out.dmg>
import os.path

application = defines["app"]  # noqa: F821 (dmgbuild supplies `defines`)
appname = os.path.basename(application)

format = "UDZO"
files = [application]
symlinks = {"Applications": "/Applications"}
# No hide_extensions: it sets Finder info on the bundle, which breaks codesign --strict.
icon = os.path.join(application, "Contents", "Resources", "AppIcon.icns")  # volume icon

background = defines["background"]  # noqa: F821 (background@2x.png next to it is used for Retina)
window_rect = ((200, 160), (640, 400))
default_view = "icon-view"
show_status_bar = show_tab_view = show_toolbar = show_pathbar = show_sidebar = False
icon_size = 128
text_size = 14
icon_locations = {appname: (170, 200), "Applications": (470, 200)}
