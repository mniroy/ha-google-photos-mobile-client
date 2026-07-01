# Changelog

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
