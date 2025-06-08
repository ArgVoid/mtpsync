# Project Plan: MTP Directory Synchronization Service

## 1. Introduction

This document serves as a comprehensive project plan and developer guide for building a Python-based CLI service that synchronizes a local directory (X) with a remote directory (Y) on a USB device via MTP. It covers architecture, directory layout, data structures, core flows, tools, and coding conventions.

---

## 2. Architecture Overview

- **Language**: Python 3.11+
- **MTP Integration**: `ctypes` bindings to `libmtp` (minimal subset) for performance
- **CLI Interface**: `argparse` or `click`
- **Concurrency**: `concurrent.futures.ThreadPoolExecutor` for parallel checksum operations
- **Logging**: Python `logging` module (rotating file handler)

### 2.1 High-Level Components

1. **CLI Entry Point** (`cli.py`) – parse args, prompt for storage, dispatch flows
2. **MTP Client** (`mtp_client.py`) – wrappers for `LIBMTP_Get_*`, upload/download, folder listing
3. **Sync Engine** (`sync.py`) – implements Verify (Flow A) and Execute (Flow B)
4. **Models & Data** (`models.py`) – path_map, id_map, execution_plan definitions
5. **Utilities** (`utils/`) – checksum, retries, config

---

## 3. Directory Structure

```plain
mtp_sync/
├── cli.py
├── mtp_client.py
├── sync.py
├── models.py
├── config.py
├── requirements.txt
├── data/
│   ├── execution_plan.json      # default plan output
│   └── .execution_retry/        # retry plans (random names)
├── logs/
│   └── sync.log
├── utils/
│   ├── checksum.py
│   ├── retries.py
│   └── prompt.py
└── tests/
    ├── test_mtp_client.py
    ├── test_sync.py
    └── fixtures/
```

- **data/**: persistent JSON plans and retry files
- **logs/**: error and info logs
- **utils/**: helper modules
- **tests/**: unit and integration tests

---

## 4. Tools & Dependencies

- **Python**: 3.11+
- **libmtp**: system library
- **ctypes**: to call minimal C APIs from `libmtp`
- **argparse** or **click**: CLI parsing
- **concurrent.futures**: thread pool
- **hashlib**: SHA256/MD5
- **pytest**: testing

Example `requirements.txt`:

```text
click>=8.0
pytest>=7.0
```

---

## 5. Data Structures

### 5.1 Path Map (`path_map`)

```python
path_map: dict[str, FolderNode]

class FolderNode:
    id: int
    type: "folder"
    children: dict[str, Union[FolderNode, FileNode]]

class FileNode:
    id: int
    type: "file"
    size: int
```

### 5.2 ID Map (`id_map`)

```python
id_map: dict[int, IDEntry]

class IDEntry:
    element: FolderNode | FileNode  # reference into path_map
    full_path: str                   # "/path/to/element"
    parent: FolderNode | None
```

### 5.3 Execution Plan (`execution_plan.json`)

JSON object mapping relative paths to types:

```json
{
  "subdir/": "dir",
  "subdir/file.txt": "file",
  ...
}
```

---

## 6. Core Flows

### 6.1 Flow A: Verify

1. **Scan source** (local FS) recursively, build plan entries (`dir` vs `file`).
2. **Scan destination** via `path_map`.
3. **For each file**:

   - If `checksum` enabled: `mtp_client.download(id)` → calculate checksum (parallel) → delete temp file
   - Else: compare sizes

4. **Build** `execution_plan.json` (default `./execution_plan.json` or via `--plan`)
5. **Output** JSON map of all mismatches or missing entries.

### 6.2 Flow B: Execute

1. **Locate plan**: CLI `--plan`, else latest in `data/.execution_retry`, else default `execution_plan.json`.
2. **If no plan**: generate full-sync plan (all files).
3. **For each entry in plan**:

   - **Dirs**: create in destination if missing via `mtp_client.mkdir(path)`
   - **Files**:

     1. Ensure parent path exists (use `path_map` cache)
     2. `mtp_client.upload(local_path, parent_id)`
     3. Download to temp → validate checksum → delete temp
     4. On failure: add to retry plan in `data/.execution_retry/{uuid}.json`

4. **Post-run**: if retry files exist, prompt user to retry now; upon success, delete retry plan.

---

## 7. CLI Interface & Flags

```bash
Usage: mtpsync [OPTIONS] SOURCE_DIR

Options:
  --dest PATH           Destination path (e.g. "/DCIM")
  --storage ID          MTP storage ID (prompted if missing)
  --mode [verify|exec]  Flow mode (verify by default)
  --checksum / --no-checksum  Validate via SHA256 (default: enabled)
  --plan PATH           Path to execution plan JSON
  -h, --help            Show help message
```

- **Interactive**: prompt for storage if `--storage` not passed

---

## 8. Storage & Initialization

1. **Detect devices**: `LIBMTP_Detect_Raw_Devices()` → `LIBMTP_Open_Raw_Device()`
2. **List storages**: `LIBMTP_Get_Storage()` → present to user
3. **Fetch file tree**: `LIBMTP_Get_Files_And_Folders(storage)` → build `path_map` & `id_map`

---

## 9. Error Handling & Logging

- **Retries**: configurable `MAX_RETRIES` with exponential backoff (`utils/retries.py`)
- **Logging**: all exceptions and MTP errors logged to `logs/sync.log`
- **Retry Plans**: failures recorded to `data/.execution_retry/*.json`

---

## 10. Testing & Quality

- **Unit tests** for `utils/*`, `models.py`
- **Integration tests** mocking `mtp_client`
- **CI**: GitHub Actions on push, run `pytest`

---

## 11. Coding Guidelines

- Minimal comments; only where complexity is high
- KISS: implement only necessary MTP methods
- Follow PEP8 & Black formatting
- Use type hints everywhere
- Break logic into small functions
- Keep files short and single purpose
