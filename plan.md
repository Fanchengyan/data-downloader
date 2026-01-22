# Implementation Plan: AIOHTTP, Chunked Download, and Unified API

This plan outlines the steps to refactor `data-downloader` to support `aiohttp`, implement concurrent chunked downloads for single files, and unify the public API.

## 1. Project Configuration & Dependencies
**File:** `pyproject.toml`
- **Action**: Add `aiohttp` to the `dependencies` list.

## 2. Enhanced Retry Logic & Logging
**File:** `data_downloader/downloader.py`
- **Action**: Refactor `RETRYABLE_STATUS_CODES` from a list to a dictionary.
  ```python
  RETRYABLE_STATUS_CODES = {
      202: "Accepted (data being prepared)",
      408: "Request Timeout",
      429: "Too Many Requests",
      500: "Internal Server Error",
      502: "Bad Gateway",
      503: "Service Unavailable",
      504: "Gateway Timeout"
  }
  ```
- **Action**: Update `_handle_status` (and other logging points) to include the status description in log messages.
  - *Format*: `">>> Server returned {code} ({reason}), will retry..."`

## 3. Remove Obsolete Multiprocessing
**File:** `data_downloader/downloader.py`
- **Action**: Remove the `mp_download_datas` function.
- **Action**: Remove the `_mp_download_data` helper function.

## 4. Core Logic Implementation

### 4.1. Helper Functions
**File:** `data_downloader/downloader.py`
- **Implement** `_auto_detect_chunks(file_size) -> int`:
  - Returns default chunk count based on file size.
  - Logic:
    - `< 10 MB`: 1 chunk
    - `10 MB - 100 MB`: 4 chunks
    - `100 MB - 1 GB`: 8 chunks
    - `> 1 GB`: 16 chunks
- **Implement** `_merge_chunks(file_path, chunks)`:
  - Concatenates part files (e.g., `filename.part0`, `filename.part1`) into the final `file_path`.
  - Deletes part files after successful merge.

### 4.2. AIOHTTP Support
**File:** `data_downloader/downloader.py`
- **Implement** `async def _download_data_aiohttp(...)`:
  - Analogous to `_download_data` (httpx) but uses `aiohttp.ClientSession`.
  - Must support the unified `retry` logic and `Retry-After` handling.

### 4.3. Chunked Download Logic
**File:** `data_downloader/downloader.py`
- **Implement** `async def _download_range(client, url, start, end, part_path, ...)`:
  - Sends a GET request with `Range: bytes={start}-{end}` header.
  - Writes response to `part_path`.
- **Implement** `async def _download_data_chunked(...)`:
  - **Inputs**: `client`, `url`, `file_path`, `chunks`, `file_size`, `retry`.
  - **Logic**:
    1. Calculate byte ranges for `chunks`.
    2. Create `chunks` tasks calling `_download_range`.
    3. Use `asyncio.gather` to run tasks concurrently.
    4. Call `_merge_chunks` upon completion.

## 5. Unified Public API Refactoring

### 5.1. `download_data` (Single File Entry Point)
**File:** `data_downloader/downloader.py`
- **Update Signature**:
  ```python
  def download_data(
      url, folder=None, file_name=None, client=None, 
      engine="requests", follow_redirects=True, retry=10, 
      authorize_from_browser=False, chunks=None
  ):
  ```
- **Logic Flow**:
  1. **Sync Engine (`requests`)**:
     - If `chunks` is specified and > 1, log warning (ignoring chunks).
     - Call `_download_data_requests`.
  2. **Async Engines (`httpx`, `aiohttp`)**:
     - This function is synchronous, so it must wrap async calls (e.g., using `asyncio.run` or existing loop).
     - **Chunk Determination**:
       - **Step 1**: If `chunks` is `None` or `0`, perform a HEAD request to get `Content-Length`.
         - Call `_auto_detect_chunks(size)`.
       - **Step 2**: 
         - If `chunks == 1`: Call sequential async downloader (`_download_data` for httpx, `_download_data_aiohttp` for aiohttp).
         - If `chunks > 1`: Call `_download_data_chunked`.

### 5.2. `batch_download_files` (Multiple Files Entry Point)
**File:** `data_downloader/downloader.py`
- **New Function**: Replaces `async_download_datas`.
- **Signature**:
  ```python
  def batch_download_files(
      urls, folder=None, file_names=None, limit=None, 
      desc="", follow_redirects=True, retry=10, 
      authorize_from_browser=False, engine="httpx", chunks=None
  ):
  ```
- **Logic**:
  - Initializes the async environment (loop).
  - Uses `asyncio.Semaphore(limit)` to control concurrency (number of files downloading at once).
  - **Per File Logic**:
    - Same determination logic as `download_data` (Check size -> Detect chunks -> Select Sequential or Chunked strategy).
    - *Note*: If `chunks > 1`, a single file download will spawn multiple sub-tasks. The `limit` should control *file* concurrency, not *chunk* concurrency.

## 6. Cleanup & Deprecation
**File:** `data_downloader/downloader.py`
- **Action**: Remove `async_download_datas`.
- **Action**: Remove `creat_tasks` (logic moved into `batch_download_files`).
- **Action**: Update `download_datas` (the simple sequential iterator) to pass the new `chunks` parameter to `download_data`.

## 7. Verification Steps
1. **Unit Test**: Test `_auto_detect_chunks` with various sizes.
2. **Integration Test**: Download a file using `engine='requests'` (Should ignore chunks).
3. **Integration Test**: Download a file using `engine='httpx'` and `chunks=1` (Sequential async).
4. **Integration Test**: Download a large file using `engine='aiohttp'` and `chunks=4` (Verify 4 part files created and merged).
5. **Integration Test**: Use `batch_download_files` to download list of files with mixed strategies.
