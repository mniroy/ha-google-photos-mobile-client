import mimetypes
import os
import re
import signal
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import nullcontext
from pathlib import Path
import typing
from typing import Literal, TypedDict

from rich.console import Group
from rich.live import Live
from rich.progress import (
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from . import utils
from .api import DEFAULT_TIMEOUT, Api
from .db import Storage
from .db_update_parser import parse_db_update
from .exceptions import SyncCycleError
from .hash_handler import calculate_sha1_hash, convert_sha1_hash
from .ha_api import HAStatusReporter

# Make Ctrl+C work for cancelling threads
signal.signal(signal.SIGINT, signal.SIG_DFL)


LogLevel = Literal["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"]


class UploadOptions(TypedDict, total=False):
    """Options for uploading a single file."""

    hash: bytes | str | None
    """The file's SHA-1 hash (bytes, hex string, or Base64 string)."""
    filename: str | None
    """Custom filename to use instead of the actual filename."""


TargetMapping = Mapping[Path, bytes | str | None | UploadOptions]


class Client:
    """Google Photos client based on reverse engineered mobile API."""

    def __init__(self, auth_data: str = "", proxy: str = "", language: str = "", timeout: int = DEFAULT_TIMEOUT, log_level: LogLevel = "INFO") -> None:
        """
        Google Photos client based on reverse engineered mobile API.

        Args:
            auth_data: Google authentication data string. If not provided, will attempt to use
                      the `GP_AUTH_DATA` environment variable.
            proxy: Proxy url `protocol://username:password@ip:port`.
            language: Accept-Language header value. If not provided, will attempt to parse from auth_data. Fallback value is `en_US`.
            log_level: Logging level to use. Must be one of "INFO", "DEBUG", "WARNING",
                      "ERROR", or "CRITICAL". Defaults to "INFO".
            timeout: Requests timeout, seconds. Defaults to DEFAULT_TIMEOUT.

        Raises:
            ValueError: If no auth_data is provided and GP_AUTH_DATA environment variable is not set.
            requests.HTTPError: If the authentication request fails.
        """
        self.logger = utils.create_logger(log_level)
        self.valid_mimetypes = ["image/", "video/"]
        self._add_raw_mimetypes()
        self.timeout = timeout
        self.auth_data = self._handle_auth_data(auth_data)
        self.language = language or utils.parse_language(self.auth_data) or "en_US"
        email = utils.parse_email(self.auth_data)
        self.logger.info(f"User: {email}")
        self.logger.info(f"Language: {self.language}")
        self.api = Api(self.auth_data, proxy=proxy, language=self.language, timeout=timeout)
        self.cache_dir = Path.home() / ".gpmc" / email
        self.db_path = self.cache_dir / "storage.db"
        self.ha_reporter = HAStatusReporter(self.logger)
        self.ha_reporter.update_state("Idle")

    def _handle_auth_data(self, auth_data: str | None) -> str:
        """
        Validate and return authentication data.

        Args:
            auth_data: Authentication data string.

        Returns:
            str: Validated authentication data.

        Raises:
            ValueError: If no auth_data is provided and GP_AUTH_DATA environment variable is not set.
        """
        if auth_data:
            return auth_data

        env_auth = os.getenv("GP_AUTH_DATA")
        if env_auth is not None:
            return env_auth

        raise ValueError("`GP_AUTH_DATA` environment variable not set. Create it or provide `auth_data` as an argument.")

    def _upload_file(
        self, file_path: str | Path, hash_value: bytes | str | None, progress: Progress, force_upload: bool, use_quota: bool, saver: bool, delete_from_host: bool = False, filename: str | None = None
    ) -> dict[str, str]:
        """
        Upload a single file to Google Photos.

        Args:
            file_path: Path to the file to upload, can be string or Path object.
            hash_value: The file's SHA-1 hash, represented as bytes, a hexadecimal string,
                    or a Base64-encoded string.
            progress: Rich Progress object for tracking upload progress.
            force_upload: Whether to upload the file even if it's already present in Google Photos.
            use_quota: Uploaded files will count against your Google Photos storage quota.
            saver: Upload files in storage saver quality.
            delete_from_host: Whether to delete the file from host immediately after successful upload.
            filename: Custom filename to use instead of the actual filename.

        Returns:
            dict[str, str]: A dictionary mapping the absolute file path to its Google Photos media key.

        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If there are issues reading the file.
            ValueError: If the file is empty or cannot be processed.
        """

        file_path = Path(file_path)
        stat = file_path.stat()
        file_size = stat.st_size
        file_mtime = int(stat.st_mtime)
        effective_filename = filename if filename else file_path.name

        if not force_upload and not hash_value:
            with Storage(self.db_path) as storage:
                cached = storage.get_local_upload(file_path.absolute().as_posix())
                if cached and cached["file_mtime"] == file_mtime and cached["file_size"] == file_size:
                    self.logger.info(f"Skipping (cached locally): {file_path.name}")
                    if delete_from_host:
                        self.logger.info(f"{file_path} deleting from host")
                        file_path.unlink()
                    return {file_path.absolute().as_posix(): cached["media_key"]}

        file_progress_id = progress.add_task(description="")
        if hash_value:
            hash_bytes, hash_b64 = convert_sha1_hash(hash_value)
        else:
            hash_bytes, hash_b64 = calculate_sha1_hash(file_path, progress, file_progress_id)
        try:
            if not force_upload:
                progress.update(task_id=file_progress_id, description=f"Checking: {file_path.name}")
                if remote_media_key := self.api.find_remote_media_by_hash(hash_bytes):
                    self.logger.info(f"Skipping (already in GP): {file_path.name}")
                    with Storage(self.db_path) as storage:
                        storage.add_local_upload(file_path.absolute().as_posix(), file_mtime, file_size, remote_media_key, hash_b64)
                    if delete_from_host:
                        self.logger.info(f"{file_path} deleting from host")
                        file_path.unlink()
                    return {file_path.absolute().as_posix(): remote_media_key}

            upload_token = self.api.get_upload_token(hash_b64, file_size)
            progress.reset(task_id=file_progress_id)
            progress.update(task_id=file_progress_id, description=f"Uploading: {file_path.name}")
            self.logger.info(f"Uploading: {file_path.name}")
            with progress.open(file_path, "rb", task_id=file_progress_id) as file:
                upload_response = self.api.upload_file(file=file, upload_token=upload_token)
            progress.update(task_id=file_progress_id, description=f"Finalizing Upload: {file_path.name}")
            last_modified_timestamp = int(file_path.stat().st_mtime)
            model = "Pixel XL"
            quality = "original"
            if saver:
                quality = "saver"
                model = "Pixel 2"
            if use_quota:
                model = "Pixel 8"
            media_key = self.api.commit_upload(
                upload_response_decoded=upload_response,
                file_name=effective_filename,
                sha1_hash=hash_bytes,
                upload_timestamp=last_modified_timestamp,
                model=model,
                quality=quality,
            )

            with Storage(self.db_path) as storage:
                storage.add_local_upload(file_path.absolute().as_posix(), file_mtime, file_size, media_key, hash_b64)

            # Delete file immediately after successful upload if requested
            if delete_from_host:
                self.logger.info(f"{file_path} deleting from host")
                file_path.unlink()

            self.logger.info(f"Success: {file_path.name}")
            return {file_path.absolute().as_posix(): media_key}
        finally:
            progress.update(file_progress_id, visible=False)
            progress.remove_task(file_progress_id)

    @staticmethod
    def _add_raw_mimetypes() -> None:
        """
        Extends Python mimetype library with RAW photo file extensions.
        """
        raw_mime_types = {
            ".arw": "image/x-sony-arw",
            ".cr2": "image/x-canon-cr2",
            ".crw": "image/x-canon-crw",
            ".dcr": "image/x-kodak-dcr",
            # '.dng': 'image/x-adobe-dng', # two of my test dng files were rejected by Google Photos API
            ".erf": "image/x-epson-erf",
            ".k25": "image/x-kodak-k25",
            ".kdc": "image/x-kodak-kdc",
            ".mrw": "image/x-minolta-mrw",
            ".nef": "image/x-nikon-nef",
            ".orf": "image/x-olympus-orf",
            ".pef": "image/x-pentax-pef",
            ".raf": "image/x-fuji-raf",
            ".raw": "image/x-panasonic-raw",
            ".sr2": "image/x-sony-sr2",
            ".srf": "image/x-sony-srf",
            ".x3f": "image/x-sigma-x3f",
        }

        for extension, mime_type in raw_mime_types.items():
            mimetypes.add_type(mime_type, extension)

    def get_media_key_by_hash(self, sha1_hash: bytes | str) -> str | None:
        """
        Get a Google Photos media key by media's hash.

        Args:
            sha1_hash: The file's SHA-1 hash, represented as bytes, a hexadecimal string,
                    or a Base64-encoded string.

        Returns:
            str | None: The Google Photos media key if found, otherwise None.
        """
        hash_bytes, _ = convert_sha1_hash(sha1_hash)
        return self.api.find_remote_media_by_hash(
            hash_bytes,
        )

    def _handle_album_creation(self, results: dict[str, str], album_name: str, show_progress: bool) -> None:
        """
        Handle album creation based on the provided album_name.

        Args:
            results: Dictionary mapping file paths to their Google Photos media keys.
            album_name: Name of album to create. "AUTO" creates albums based on parent directories.
            show_progress: Whether to display progress in the console.
        """
        if album_name != "AUTO":
            # Add all media keys to the specified album
            media_keys = list(results.values())
            self.add_to_album(media_keys, album_name, show_progress=show_progress)
            return

        # Group media keys by the full path of their parent directory
        media_keys_by_album = {}
        for file_path, media_key in results.items():
            parent_dir = Path(file_path).parent.resolve().as_posix()
            if parent_dir not in media_keys_by_album:
                media_keys_by_album[parent_dir] = []
            media_keys_by_album[parent_dir].append(media_key)

        for parent_dir, media_keys in media_keys_by_album.items():
            album_name_from_path = Path(parent_dir).name  # Use the directory name as the album name
            self.add_to_album(media_keys, album_name_from_path, show_progress=show_progress)

    @staticmethod
    def _filter_files(expression: str, filter_exclude: bool, filter_regex: bool, filter_ignore_case: bool, filter_path: bool, paths: typing.Iterable[Path]) -> typing.Iterator[Path]:
        """
        Filter a list of Path objects based on a filter expression.

        Args:
            expression: The filter expression to match against.
            filter_exclude: If True, exclude matching files.
            filter_regex: If True, treat expression as regex.
            filter_ignore_case: If True, perform case-insensitive matching.
            filter_path: If True, check full path instead of just filename.
            paths: Iterable of Path objects to filter.

        Yields:
            Path: Filtered Path objects.
        """
        for path in paths:
            text_to_check = str(path) if filter_path else str(path.name)

            if filter_regex:
                flags = re.IGNORECASE if filter_ignore_case else 0
                matches = bool(re.search(expression, text_to_check, flags))
            else:
                matches = expression.lower() in text_to_check.lower() if filter_ignore_case else expression in text_to_check

            if (matches and not filter_exclude) or (not matches and filter_exclude):
                yield path

    def upload(
        self,
        target: str | Path | Sequence[str | Path] | TargetMapping,
        album_name: str | None = None,
        use_quota: bool = False,
        saver: bool = False,
        recursive: bool = False,
        show_progress: bool = False,
        threads: int = 1,
        force_upload: bool = False,
        delete_from_host: bool = False,
        filter_exp: str = "",
        filter_exclude: bool = False,
        filter_regex: bool = False,
        filter_ignore_case: bool = False,
        filter_path: bool = False,
        batch_size: int = 1000,
    ) -> dict[str, str]:
        """
        Upload one or more files or directories to Google Photos.

        Args:
            target: A file path, directory path, a sequence of such paths, or a mapping of file paths
                to their upload options. Upload options can be:
                - A SHA-1 hash (bytes, hex string, or Base64 string)
                - None (hash will be calculated)
                - An UploadOptions dict with 'hash' and/or 'filename' keys

                Example with custom filename:
                    {Path("/path/to/file.jpg"): {"hash": None, "filename": "custom_name.jpg"}}

            album_name:
                If provided, the uploaded media will be added to a new album.
                If set to "AUTO", albums will be created based on the immediate parent directory of each file.

                "AUTO" Example:
                    - When uploading '/foo':
                        - '/foo/image1.jpg' will be placed in a 'foo' album.
                        - '/foo/bar/image2.jpg' will be placed in a 'bar' album.
                        - '/foo/bar/foo/image3.jpg' will be placed in a 'foo' album, distinct from the first 'foo' album.

                Defaults to None.
            use_quota: Uploaded files will count against your Google Photos storage quota. Defaults to False.
            saver: Upload files in storage saver quality. Defaults to False.
            recursive: Whether to recursively search for media files in subdirectories.
                                Only applies when uploading directories. Defaults to False.
            show_progress: Whether to display upload progress in the console. Defaults to False.
            threads: Number of concurrent upload threads for multiple files. Defaults to 1.
            force_upload: Whether to upload files even if they're already present in
                                Google Photos (based on hash). Defaults to False.
            delete_from_host: Whether to delete each file immediately after its individual upload completes.
                                    Defaults to False.
            filter_exp: The filter expression to match against filenames or paths.
            filter_exclude: If True, exclude files matching the filter.
            filter_regex: If True, treat the expression as a regular expression.
            filter_ignore_case: If True, perform case-insensitive matching.
            filter_path: If True, check for matches in the full path instead of just the filename.

        Returns:
            dict[str, str]: A dictionary mapping absolute file paths to their Google Photos media keys.
                            Example: {
                                "/path/to/photo1.jpg": "media_key_123",
                                "/path/to/photo2.jpg": "media_key_456"
                            }

        Raises:
            TypeError: If `target` is not a file path, directory path, or a sequence of such paths.
            ValueError: If no valid media files are found to upload.
        """
        self.ha_reporter.update_state("Initializing")
        try:
            path_hash_iterator = self._handle_target_input(
                target,
                recursive,
                filter_exp,
                filter_exclude,
                filter_regex,
                filter_ignore_case,
                filter_path,
            )

            results = {}
            if batch_size <= 0:
                path_hash_pairs = dict(path_hash_iterator)
                if not path_hash_pairs:
                    raise ValueError("No valid media files found to upload.")
                results = self._upload_concurrently(
                    path_hash_pairs,
                    threads=threads,
                    show_progress=show_progress,
                    force_upload=force_upload,
                    use_quota=use_quota,
                    saver=saver,
                    delete_from_host=delete_from_host,
                )
                if album_name:
                    self.ha_reporter.update_state("Adding to album")
                    self._handle_album_creation(results, album_name, show_progress)
            else:
                import itertools
                batch_count = 0
                while True:
                    batch = dict(itertools.islice(path_hash_iterator, batch_size))
                    if not batch:
                        if batch_count == 0:
                            raise ValueError("No valid media files found to upload.")
                        break
                    batch_count += 1
                    self.logger.info(f"Processing batch {batch_count} of size {len(batch)}...")
                    batch_results = self._upload_concurrently(
                        batch,
                        threads=threads,
                        show_progress=show_progress,
                        force_upload=force_upload,
                        use_quota=use_quota,
                        saver=saver,
                        delete_from_host=delete_from_host,
                    )
                    if album_name:
                        self.ha_reporter.update_state("Adding to album")
                        self._handle_album_creation(batch_results, album_name, show_progress)
                    results.update(batch_results)

            self.ha_reporter.update_state("Completed", {"total": len(results), "uploaded": len(results), "errors": 0})
            return results
        except Exception as e:
            self.ha_reporter.update_state("Error", {"error_message": str(e)})
            raise

    def _handle_target_input(
        self,
        target: str | Path | Sequence[str | Path] | TargetMapping,
        recursive: bool,
        filter_exp: str,
        filter_exclude: bool,
        filter_regex: bool,
        filter_ignore_case: bool,
        filter_path: bool,
    ) -> typing.Iterator[tuple[Path, typing.Any]]:
        """
        Process and validate the upload target input into a consistent path-hash mapping generator.

        Args:
            target: A file path, directory path, sequence of paths, or mapping of paths to hashes.
            recursive: Whether to search directories recursively for media files.
            filter_exp: The filter expression to match against filenames or paths.
            filter_exclude: If True, exclude files matching the filter.
            filter_regex: If True, treat the expression as a regular expression.
            filter_ignore_case: If True, perform case-insensitive matching.
            filter_path: If True, check for matches in the full path instead of just the filename.

        Yields:
            tuple[Path, typing.Any]: A tuple of file path and its upload options or hash.
        """
        if isinstance(target, (str, Path)):
            target = [target]

        if isinstance(target, Sequence) and all(isinstance(p, (str, Path)) for p in target):
            def file_generator():
                for p in target:
                    yield from self._search_for_media_files(p, recursive=recursive)

            self.ha_reporter.update_state("Scanning directories")
            files_to_upload = file_generator()

            if filter_exp:
                self.ha_reporter.update_state("Filtering files")
                files_to_upload = self._filter_files(filter_exp, filter_exclude, filter_regex, filter_ignore_case, filter_path, files_to_upload)

            for path in files_to_upload:
                yield path, None

        elif isinstance(target, dict) and all(isinstance(k, Path) and isinstance(v, (bytes, str, dict, type(None))) for k, v in target.items()):
            for k, v in target.items():
                yield k, v
        else:
            raise TypeError("`target` must be a file path, a directory path, or a sequence of such paths.")

    def _search_for_media_files(self, path: str | Path, recursive: bool):
        """
        Search for valid media files in the specified path.

        Args:
            path: File or directory path to search for media files.
            recursive: Whether to search subdirectories recursively. Only applies
                             when path is a directory.

        Yields:
            Path: Path objects pointing to valid media files.

        Raises:
            ValueError: If the path is invalid, or if a single file's mime type is not supported.
        """
        path = Path(path)

        if path.is_file():
            if any(mimetype_guess is not None and mimetype_guess.startswith(mimetype) for mimetype in self.valid_mimetypes if (mimetype_guess := mimetypes.guess_type(path)[0])):
                yield path
                return
            raise ValueError("File's mime type does not match image or video mime type.")

        if not path.is_dir():
            raise ValueError("Invalid path. Please provide a file or directory path.")

        self.logger.info(f"Scanning directory {path} (recursive={recursive})... This might take a while for large folders.")

        count = 0
        media_count = 0

        def _is_media(f_path: Path) -> bool:
            if not f_path.is_file():
                return False
            mimetype_guess = mimetypes.guess_type(f_path)[0]
            if mimetype_guess is None:
                return False
            return any(mimetype_guess.startswith(mimetype) for mimetype in self.valid_mimetypes)

        if recursive:
            for root, _, filenames in os.walk(path):
                for filename in filenames:
                    file_path = Path(root) / filename
                    count += 1
                    if count % 1000 == 0:
                        self.logger.info(f"Still scanning... found {count} files so far in {root}")
                    if _is_media(file_path):
                        media_count += 1
                        yield file_path
        else:
            for file_path in path.iterdir():
                count += 1
                if count % 1000 == 0:
                    self.logger.info(f"Still scanning... found {count} files so far in {path}")
                if _is_media(file_path):
                    media_count += 1
                    yield file_path

        self.logger.info(f"Scanned {count} total files. Found {media_count} media files to process.")

    def _calculate_hash(self, file_path: Path, progress: Progress) -> tuple[Path, bytes]:
        hash_calc_progress_id = progress.add_task(description="Calculating hash")
        try:
            hash_bytes, _ = calculate_sha1_hash(file_path, progress, hash_calc_progress_id)
            return file_path, hash_bytes
        finally:
            progress.update(hash_calc_progress_id, visible=False)
            progress.remove_task(hash_calc_progress_id)

    def _upload_concurrently(self, path_hash_pairs: TargetMapping, threads: int, show_progress: bool, force_upload: bool, use_quota: bool, saver: bool, delete_from_host: bool) -> dict[str, str]:
        """
        Upload files concurrently to Google Photos.

        Args:
            path_hash_pairs: Mapping of file paths to their upload options (hash and/or filename)
                or just hashes for backwards compatibility.
            threads: Number of concurrent upload threads.
            show_progress: Whether to display progress in console.
            force_upload: Upload even if file exists in Google Photos.
            use_quota: Count uploads against storage quota.
            saver: Upload in storage saver quality.
            delete_from_host: Delete each file immediately after successful upload.

        Returns:
            dict[str, str]: Dictionary mapping file paths to media keys.

        Note:
            Failed uploads are logged but don't stop the overall process.
        """
        uploaded_files = {}
        overall_progress = Progress(
            TextColumn("[bold yellow]Files processed:"),
            SpinnerColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("{task.description}"),
        )
        file_progress = Progress(
            DownloadColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            TransferSpeedColumn(),
            TextColumn("{task.description}"),
        )
        upload_error_count = 0
        progress_group = Group(
            file_progress,
            overall_progress,
        )

        context = (show_progress and Live(progress_group)) or nullcontext()

        overall_task_id = overall_progress.add_task("Errors: 0", total=len(path_hash_pairs.keys()), visible=show_progress)
        total_files = len(path_hash_pairs.keys())
        uploaded_count = 0
        self.ha_reporter.update_state(f"Uploading 0/{total_files}", {"total": total_files, "uploaded": 0, "errors": upload_error_count})
        
        with context, ThreadPoolExecutor(max_workers=threads) as executor:
            active_futures = {}
            path_hash_iter = iter(path_hash_pairs.items())

            def submit_next():
                try:
                    path, value = next(path_hash_iter)
                    if isinstance(value, dict):
                        hash_value = value.get("hash")
                        filename = value.get("filename")
                    else:
                        hash_value = value
                        filename = None
                    future = executor.submit(
                        self._upload_file, path, hash_value, progress=file_progress, force_upload=force_upload, use_quota=use_quota, saver=saver, delete_from_host=delete_from_host, filename=filename
                    )
                    active_futures[future] = (path, value)
                    return True
                except StopIteration:
                    return False

            # Initial submit up to max_workers * 2
            for _ in range(threads * 2):
                if not submit_next():
                    break

            while active_futures:
                done, _ = wait(active_futures.keys(), return_when=FIRST_COMPLETED)

                for future in done:
                    target = active_futures.pop(future)
                    try:
                        media_key_dict = future.result()
                        uploaded_files = uploaded_files | media_key_dict
                        uploaded_count += 1
                    except Exception as e:
                        self.logger.error(f"Error uploading file {target[0]}: {e}")
                        upload_error_count += 1
                        overall_progress.update(task_id=overall_task_id, description=f"[bold red] Errors: {upload_error_count}")
                    finally:
                        overall_progress.advance(overall_task_id)
                        self.ha_reporter.update_state(f"Uploading {uploaded_count}/{total_files}", {"total": total_files, "uploaded": uploaded_count, "errors": upload_error_count})

                    # Submit a new task to replace the completed one
                    submit_next()
        return uploaded_files

    def move_to_trash(self, sha1_hashes: str | bytes | Sequence[str | bytes]) -> dict:
        """
        Move remote media files to trash.

        Args:
            sha1_hashes: Single SHA-1 hash or sequence of hashes to move to trash.

        Returns:
            dict: API response containing operation results.

        Raises:
            ValueError: If input hashes are invalid.
        """

        if isinstance(sha1_hashes, (str, bytes)):
            sha1_hashes = [sha1_hashes]

        try:
            # Convert all hashes to Base64 format
            hashes_b64 = [convert_sha1_hash(hash)[1] for hash in sha1_hashes]  # type: ignore
            dedup_keys = [utils.urlsafe_base64(hash) for hash in hashes_b64]
        except (TypeError, ValueError) as e:
            raise ValueError("Invalid SHA-1 hash format") from e

        # Process in batches of 500 to avoid API limits
        batch_size = 500
        response = {}
        for i in range(0, len(dedup_keys), batch_size):
            batch = dedup_keys[i : i + batch_size]
            batch_response = self.api.move_remote_media_to_trash(dedup_keys=batch)
            response.update(batch_response)  # Combine responses if needed

        return response

    def add_to_album(self, media_keys: Sequence[str], album_name: str, show_progress: bool) -> list[str]:
        """
        Add media items to one or more albums with the given name. If the total number of items exceeds the album limit,
        additional albums with numbered suffixes are created. The first album will also have a suffix if there are multiple albums.

        Args:
            media_keys: Media keys of the media items to be added to album.
            album_name: Album name.
            show_progress : Whether to display upload progress in the console.

        Returns:
            list[str]: Album media keys for all created albums.

        Raises:
            requests.HTTPError: If the API request fails.
            ValueError: If media_keys is empty.
        """
        album_limit = 20000  # Maximum number of items per album
        batch_size = 500  # Number of items to process per API call
        album_keys = []
        album_counter = 1

        if len(media_keys) > album_limit:
            self.logger.warning(f"{len(media_keys)} items exceed the album limit of {album_limit}. They will be split into multiple albums.")

        # Initialize progress bar
        progress = Progress(
            TextColumn("{task.description}"),
            SpinnerColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        )
        task = progress.add_task(f"[bold yellow]Adding items to album[/bold yellow] [cyan]{album_name}[/cyan]:", total=len(media_keys))

        context = (show_progress and Live(progress)) or nullcontext()

        with context:
            for i in range(0, len(media_keys), album_limit):
                album_batch = media_keys[i : i + album_limit]
                # Add a suffix if media_keys will not fit into a single album
                current_album_name = f"{album_name} {album_counter}" if len(media_keys) > album_limit else album_name
                current_album_key = None
                for j in range(0, len(album_batch), batch_size):
                    batch = album_batch[j : j + batch_size]
                    if current_album_key is None:
                        # Create the album with the first batch
                        current_album_key = self.api.create_album(album_name=current_album_name, media_keys=batch)
                        album_keys.append(current_album_key)
                    else:
                        # Add to the existing album
                        self.api.add_media_to_album(album_media_key=current_album_key, media_keys=batch)
                    progress.update(task, advance=len(batch))
                album_counter += 1
        return album_keys

    def update_cache(self, show_progress: bool = True, max_sync_cycles: int = 10):
        """
        Incrementally update local library cache.

        This implements the sync logic reverse engineered from the Google Photos app:
        1. Initial sync: Full library download with pagination (resume_token)
        2. Delta sync: Incremental updates using sync_token with cycle detection

        Args:
            show_progress: Whether to display progress in console.
            max_sync_cycles: Maximum sync cycles for delta sync (prevents infinite loops).
                            Based on Google Photos app's sync cycle detection logic.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        progress = Progress(
            TextColumn("{task.description}"),
            SpinnerColumn(),
            "Updates: [green]{task.fields[updated]:>8}[/green]",
            "Deletions: [red]{task.fields[deleted]:>8}[/red]",
            "Pages: [cyan]{task.fields[pages]:>6}[/cyan]",
        )
        task_id = progress.add_task(
            "[bold magenta]Updating local cache[/bold magenta]:",
            updated=0,
            deleted=0,
            pages=0,
        )
        context = (show_progress and Live(progress)) or nullcontext()

        with context:
            # Get saved state tokens
            with Storage(self.db_path) as storage:
                init_state = storage.get_init_state()

            if not init_state:
                self.logger.info("Cache Initiation")
                self._cache_init(progress, task_id)
                with Storage(self.db_path) as storage:
                    storage.set_init_state(1)
            self.logger.info("Cache Update")
            self._cache_update(progress, task_id, max_sync_cycles)

    def _cache_update(self, progress, task_id, max_sync_cycles: int = 10):
        """
        Perform delta sync to update the cache with changes since last sync.

        Args:
            progress: Rich Progress object for tracking.
            task_id: ID of the progress task.
            max_sync_cycles: Maximum number of sync cycles to prevent infinite loops.
                             Based on Google Photos app behavior that detects when
                             sync_token doesn't change between iterations.
        """
        sync_cycle_count = 0
        previous_sync_token = None

        while sync_cycle_count < max_sync_cycles:
            with Storage(self.db_path) as storage:
                sync_token, _ = storage.get_sync_tokens()

            # Infinite sync cycle detection (from Google Photos app logic):
            # If shouldTriggerNextSync is true but sync token hasn't changed,
            # stop to avoid infinite sync loop
            if previous_sync_token and sync_token == previous_sync_token:
                self.logger.warning(f"Sync token unchanged after {sync_cycle_count} cycles. Stopping to avoid infinite sync loop.")
                raise SyncCycleError(f"Sync token unchanged after {sync_cycle_count} cycles. sync_token={sync_token[:50]}...")

            response = self.api.get_library_state(sync_token)
            next_sync_token, next_resume_token, remote_media, media_keys_to_delete = parse_db_update(response)

            with Storage(self.db_path) as storage:
                storage.update_sync_tokens(next_sync_token, next_resume_token)
                storage.update(remote_media)
                storage.delete(media_keys_to_delete)

            task = progress.tasks[int(task_id)]
            progress.update(
                task_id,
                updated=task.fields["updated"] + len(remote_media),
                deleted=task.fields["deleted"] + len(media_keys_to_delete),
            )

            # Process remaining pages for this sync cycle
            if next_resume_token:
                self._process_pages(progress, task_id, sync_token, next_resume_token)

            # Check if we need another sync cycle
            # Google Photos app triggers next sync when server indicates more data
            should_continue = self._should_trigger_next_sync(response)
            if not should_continue:
                break

            previous_sync_token = sync_token
            sync_cycle_count += 1
            self.logger.debug(f"Triggering sync cycle {sync_cycle_count + 1}")

    def _should_trigger_next_sync(self, response: dict) -> bool:
        """
        Determine if another sync cycle should be triggered.

        Based on Google Photos app behavior, this checks if the server
        indicates there's more data to sync.

        Args:
            response: The sync response from the API.

        Returns:
            bool: True if another sync should be triggered.
        """
        # Check for the continuation indicator in the response
        # Field 1.7 typically indicates if sync should continue (value 2 = continue)
        try:
            trigger_value = response.get("1", {}).get("7", 0)
            return trigger_value == 2
        except (KeyError, TypeError):
            return False

    def _cache_init(self, progress, task_id):
        """
        Perform initial sync to populate the cache with the full library.

        Based on Google Photos app behavior:
        - Initial sync fetches the complete library state
        - Uses resume_token for pagination
        - Sets sync_token upon completion for future delta syncs

        Args:
            progress: Rich Progress object for tracking.
            task_id: ID of the progress task.
        """
        with Storage(self.db_path) as storage:
            sync_token, resume_token = storage.get_sync_tokens()

        # Resume incomplete initial sync if there's a pending resume token
        if resume_token:
            self.logger.info("Resuming incomplete initial sync")
            self._process_pages_init(progress, task_id, resume_token)

        response = self.api.get_library_state(sync_token)
        sync_token, resume_token, remote_media, _ = parse_db_update(response)

        with Storage(self.db_path) as storage:
            storage.update_sync_tokens(sync_token, resume_token)
            storage.update(remote_media)

        task = progress.tasks[int(task_id)]
        progress.update(
            task_id,
            updated=task.fields["updated"] + len(remote_media),
            pages=task.fields["pages"] + 1,
        )

        self.logger.debug(f"Initial sync first page: {len(remote_media)} items")

        if resume_token:
            self._process_pages_init(progress, task_id, resume_token)

    def _process_pages_init(self, progress: Progress, task_id: TaskID, resume_token: str):
        """
        Process paginated results during initial sync.

        Based on Google Photos app behavior:
        - Initial sync uses resume_token for pagination
        - No sync_token is required during initial sync
        - Pages are fetched until resume_token is empty

        Args:
            progress: Rich Progress object for tracking.
            task_id: ID of the progress task.
            resume_token: Resume token for fetching next page of results.
        """
        next_resume_token: str | None = resume_token
        page_count = 0
        while True:
            response = self.api.get_library_page_init(next_resume_token)
            _, next_resume_token, remote_media, media_keys_to_delete = parse_db_update(response)
            page_count += 1

            with Storage(self.db_path) as storage:
                storage.update_sync_tokens(resume_token=next_resume_token)
                storage.update(remote_media)
                storage.delete(media_keys_to_delete)

            task = progress.tasks[int(task_id)]
            progress.update(
                task_id,
                updated=task.fields["updated"] + len(remote_media),
                deleted=task.fields["deleted"] + len(media_keys_to_delete),
                pages=task.fields["pages"] + 1,
            )

            self.logger.debug(f"Initial sync page {page_count}: {len(remote_media)} items")

            if not next_resume_token:
                break

    def _process_pages(self, progress: Progress, task_id: TaskID, sync_token: str, resume_token: str):
        """
        Process paginated results during delta sync.

        Based on Google Photos app behavior:
        - Delta sync uses both sync_token and resume_token
        - sync_token identifies the sync context
        - resume_token is used for pagination within that sync cycle
        - Pages are fetched until resume_token is empty

        Args:
            progress: Rich Progress object for tracking.
            task_id: ID of the progress task.
            sync_token: Current sync token for the delta sync context.
            resume_token: Resume token for fetching next page of results.
        """
        next_resume_token: str | None = resume_token
        page_count = 0
        while True:
            response = self.api.get_library_page(next_resume_token, sync_token)
            _, next_resume_token, remote_media, media_keys_to_delete = parse_db_update(response)
            page_count += 1

            with Storage(self.db_path) as storage:
                storage.update_sync_tokens(resume_token=next_resume_token)
                storage.update(remote_media)
                storage.delete(media_keys_to_delete)

            task = progress.tasks[int(task_id)]
            progress.update(
                task_id,
                updated=task.fields["updated"] + len(remote_media),
                deleted=task.fields["deleted"] + len(media_keys_to_delete),
                pages=task.fields["pages"] + 1,
            )

            self.logger.debug(f"Delta sync page {page_count}: {len(remote_media)} items, {len(media_keys_to_delete)} deletions")

            if not next_resume_token:
                break
