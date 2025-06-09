"""
CLI entry point for MTP Directory Synchronization Service.
Handles command line arguments and dispatches to appropriate flows.
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, List

from mtp_client import MTPClient
from sync import SyncEngine
from utils.prompt import prompt_choice, prompt_yes_no, display_progress
from config import DEFAULT_EXECUTION_PLAN, LOG_FILE


def setup_logging(log_level: str) -> None:
    """Configure logging with the specified level."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.debug(f"Logging initialized at level {log_level}")


def setup_arg_parser() -> argparse.ArgumentParser:
    """
    Set up command line argument parser.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="mtpsync",
        description="MTP Directory Synchronization Service"
    )
    
    parser.add_argument(
        'source_dir',
        metavar='SOURCE_DIR',
        help='Source directory to synchronize'
    )
    
    parser.add_argument(
        '--dest',
        metavar='PATH',
        help='Destination path on MTP device (e.g. "/DCIM")',
        default='/'
    )
    
    parser.add_argument(
        '--storage',
        metavar='ID',
        type=int,
        help='MTP storage ID (prompted if missing)'
    )
    
    parser.add_argument(
        '--mode',
        choices=['verify', 'exec'],
        default='verify',
        help='Flow mode (verify by default)'
    )
    
    parser.add_argument(
        '--checksum',
        dest='use_checksum',
        action='store_true',
        help='Validate via SHA256 (default: enabled)'
    )
    
    parser.add_argument(
        '--no-checksum',
        dest='use_checksum',
        action='store_false',
        help='Skip checksum validation'
    )
    parser.set_defaults(use_checksum=True)
    
    parser.add_argument(
        '--plan',
        metavar='PATH',
        help='Path to execution plan JSON',
        type=Path
    )
    
    parser.add_argument(
        '--log-level',
        choices=['debug', 'info', 'warning', 'error', 'critical'],
        default='info',
        help='Set the logging level (default: info)'
    )
    
    return parser


def select_device(mtp_client: MTPClient) -> dict:
    """Select MTP device to use.
    
    Args:
        mtp_client: MTP client instance
        
    Returns:
        Selected device info dictionary
    """
    devices = mtp_client.detect_devices()
    
    if not devices:
        raise RuntimeError("No MTP devices found")
        
    if len(devices) == 1:
        device = devices[0]
        print("Using first available MTP device")
        return device
        
    print("\nAvailable devices:")
    for i, device in enumerate(devices):
        print(f"{i+1}. MTP device {i+1}")
        
    while True:
        try:
            choice = int(input("\nSelect device (1-{len(devices)}): "))
            if 1 <= choice <= len(devices):
                return devices[choice-1]
        except ValueError:
            pass
            
        print(f"\nInvalid choice. Please enter a number between 1 and {len(devices)}")


def select_storage(mtp_client: MTPClient, storage_id: Optional[int] = None) -> dict:
    """
    Get available storages and prompt user to select one if storage_id not provided.
    
    Args:
        mtp_client: Connected MTP client
        storage_id: Optional specific storage ID to use
        
    Returns:
        Selected storage info
    """
    storages = mtp_client.get_storages()
    
    if not storages:
        logger.error("No storage found on device")
        print("Error: No storage found on the connected device.")
        sys.exit(1)
    
    # If storage ID provided, find matching storage
    if storage_id is not None:
        for storage in storages:
            if storage['id'] == storage_id:
                print(f"Using storage: {storage['desc']}")
                return storage
        
        logger.error(f"Storage ID {storage_id} not found")
        print(f"Error: Storage ID {storage_id} not found on device.")
        sys.exit(1)
    
    # If only one storage, use it
    if len(storages) == 1:
        storage = storages[0]
        print(f"Using storage: {storage['desc']}")
        return storage
    
    # Format storage info for display
    def format_storage(storage):
        capacity_gb = storage['capacity'] / (1024**3)
        free_space_gb = storage['free_space'] / (1024**3)
        return f"{storage['desc']} ({capacity_gb:.1f} GB, {free_space_gb:.1f} GB free)"
    
    return prompt_choice("Select storage:", storages, format_storage)


def main():
    """Main entry point."""
    parser = setup_arg_parser() 
    args = parser.parse_args()
    
    # Set up logging with specified level
    logger = setup_logging(args.log_level)
    
    try:
        # Initialize MTP client
        mtp_client = MTPClient()
        
        # Select device and storage
        device = select_device(mtp_client)
        mtp_client.open_device(device)
        
        storage = select_storage(mtp_client, args.storage)
        storage_id = storage['id']
        
        print(f"Building file tree for {storage['desc']}...")
        path_map, id_map = mtp_client.build_file_tree(storage_id, args.dest)
        
        # Initialize sync engine
        source_dir = Path(args.source_dir)
        sync_engine = SyncEngine(
            mtp_client=mtp_client,
            source_dir=source_dir,
            dest_path=args.dest,
            use_checksum=args.use_checksum,
            storage_id=storage_id
        )
        
        # Execute flow based on selected mode
        if args.mode == 'verify':
            print(f"Verifying source directory {source_dir} against {args.dest}...")
            plan_path = sync_engine.verify(args.plan)
            print(f"Execution plan generated: {plan_path}")
            
            # Ask if user wants to execute the plan now
            if prompt_yes_no("Execute sync plan now?"):
                success, retry_path = sync_engine.execute(plan_path)
                if success:
                    print("Sync completed successfully.")
                else:
                    print(f"Sync completed with errors. Retry plan saved to: {retry_path}")
            
        else:  # args.mode == 'exec'
            print(f"Executing sync from {source_dir} to {args.dest}...")
            success, retry_path = sync_engine.execute(args.plan)
            
            if success:
                print("Sync completed successfully.")
            else:
                print(f"Sync completed with errors. Retry plan saved to: {retry_path}")
                
                # Ask if user wants to retry failed items
                if retry_path and prompt_yes_no("Retry failed items now?"):
                    print("Retrying failed items...")
                    retry_success, new_retry_path = sync_engine.execute(retry_path)
                    
                    if retry_success:
                        print("Retry completed successfully.")
                    else:
                        print(f"Retry completed with errors. New retry plan saved to: {new_retry_path}")
    
    except Exception as e:
        logger.exception("Error in MTP sync")
        print(f"Error: {str(e)}")
        sys.exit(1)
    
    finally:
        # Close MTP client connection
        if 'mtp_client' in locals() and mtp_client:
            mtp_client.close()


if __name__ == "__main__":
    main()
