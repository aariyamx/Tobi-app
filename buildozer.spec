[app]
title = Tobi
package.name = tobi
package.domain = org.tobi
source.dir = .
source.include_exts = py
source.exclude_dirs = .github,bin,.buildozer
version = 0.1

# sqlite3 = memory database, the rest are what 'requests' needs for HTTPS
requirements = python3,kivy==2.3.1,requests,urllib3,idna,charset-normalizer==2.1.1,certifi,openssl,sqlite3

orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
