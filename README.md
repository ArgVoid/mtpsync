# MTP Directory Synchronization Service

A Python-based CLI service that synchronizes a local directory with a remote directory on a USB device via MTP.

## Features

- Synchronize files and folders from local storage to MTP devices (like Android phones, digital cameras, etc.)
- Verify-only option to check what will be synchronized before making changes
- Checksum validation to ensure file integrity
- Support for automatic retry of failed transfers
- Interactive device and storage selection

## Requirements

- Python 3.11+
- libmtp (system library)

## Installation

1. Install libmtp on your system:

   - **MacOS**: `brew install libmtp`
   - **Ubuntu/Debian**: `sudo apt-get install libmtp-dev`
   - **Fedora/RHEL**: `sudo dnf install libmtp-devel`
   - **Windows**: [Download and install libmtp](https://libmtp.sourceforge.net/)

2. Install the Python package requirements:

   ```
   pip install -r mtpsync/requirements.txt
   ```

## Usage

Basic usage:

```bash
python -m mtpsync.cli /path/to/source/directory
```

This will:
1. Detect MTP devices
2. Prompt for device selection if multiple are connected
3. Prompt for storage selection if multiple are available
4. Verify the differences between source and destination
5. Generate an execution plan
6. Ask if you want to proceed with synchronization

### Command Line Options

```
Usage: mtpsync [OPTIONS] SOURCE_DIR

Options:
  --dest PATH           Destination path (e.g. "/DCIM")
  --storage ID          MTP storage ID (prompted if missing)
  --mode [verify|exec]  Flow mode (verify by default)
  --checksum / --no-checksum  Validate via SHA256 (default: enabled)
  --plan PATH           Path to execution plan JSON
  -h, --help            Show help message
```

### Examples

Synchronize a photo directory to the DCIM folder on your device:
```bash
python -m mtpsync.cli ~/Pictures/vacation --dest /DCIM/vacation
```

Verify what will be synchronized without transferring any files:
```bash
python -m mtpsync.cli ~/Documents/important --mode verify
```

Execute a previously generated sync plan:
```bash
python -m mtpsync.cli ~/Music --mode exec --plan ./custom_plan.json
```

## Development

### Project Structure

```
mtpsync/
├── cli.py            - Command line interface
├── mtp_client.py     - Libmtp bindings and client
├── sync.py           - Synchronization engine
├── models.py         - Data structures
├── config.py         - Configuration and constants
├── utils/            - Utility functions
│   ├── checksum.py   - File checksum utilities
│   ├── retries.py    - Retry logic
│   └── prompt.py     - User interaction
├── data/             - Execution plans
└── logs/             - Log files
```

### Testing

Run tests using pytest:

```bash
pytest
```
