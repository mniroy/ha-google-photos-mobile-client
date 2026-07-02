# Changelog

## 1.0.21
- **CRITICAL FIX**: Fixed a fatal batching indentation bug that caused the addon to successfully find all photos but then instantly exit without uploading them if `batch_size` was used.
- Fixed the local database being wiped every time the addon restarts by moving `storage.db` to Home Assistant's persistent `/data` directory.
- Fixed symlink traversal so `os.walk` now correctly follows symlinks in the target directory.
## 1.0.20
- Fix "silent crash" where the add-on would stop immediately without any logs when the upload target directory was empty or when the user set the log level to WARNING/ERROR, filtering out the startup messages.
- Fix severe performance issue during the fast pre-scan phase where the addon was unnecessarily computing the SHA1 hash of every file just to count them.

## 1.0.19
- Cleanup unnecessary bash debug traces that were spamming addon logs in 1.0.18.

## 1.0.18
- Revert `log_level` to text input to fix a fatal Home Assistant Supervisor crash affecting existing users due to saved string config schema mismatches.

## 1.0.17
- Fix schema syntax for log_level dropdown menu.

## 1.0.16
- Changed `log_level` configuration schema from a text input to a drop-down menu for better usability in the Home Assistant UI.

## 1.0.15
- Fix silent crash on startup caused by Home Assistant trying to eagerly read optional config values (like batch size and log level) before users had saved them in the UI.

## 1.0.14
- Add fast pre-scan to determine overall total files for accurate cumulative progress tracking.
- Throttle Home Assistant sensor updates to 10 minutes to prevent database bloat.

## 1.0.13
- Implement local cache to skip hashing and API checks for already uploaded files, massively reducing disk I/O and startup time for large libraries.

## 1.0.12
- Fix missing typing import that caused startup crashes.

## 1.0.11
- Implement batching for uploads to fix OOM crash when processing huge folders.
- Add log_level setting to control log verbosity.

## 1.0.10
- Fix memory leak caused by uncollected progress tasks over long upload sessions.

## 1.0.9
- Throttle Home Assistant sensor updates to prevent overwhelming the state machine.
- Add unique_id to sensor attributes.

## 1.0.2
- Fix update version bug. Add progress output.

## 1.0.0
- Initial release of Google Photos Mobile Client as Home Assistant Add-on.
- Support for album selection and recursive folder uploads.
- Shows upload progress in logs.
