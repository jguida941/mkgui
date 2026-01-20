"""Sample script with argparse for testing entrypoint detection."""

import argparse
from pathlib import Path


def main():
    """Main entry point using argparse.

    This demonstrates argparse-based CLI detection.
    """
    parser = argparse.ArgumentParser(description="Process some files")
    parser.add_argument("input_file", type=Path, help="Input file path")
    parser.add_argument("--output", "-o", type=Path, help="Output file path")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually do anything")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers")

    args = parser.parse_args()

    print(f"Processing {args.input_file}")
    if args.output:
        print(f"Output to {args.output}")


def run(config_path: Path, debug: bool = False) -> dict:
    """Alternative entrypoint function.

    Args:
        config_path: Path to config file
        debug: Enable debug mode

    Returns:
        Processing result dictionary
    """
    return {"status": "ok", "config": str(config_path)}


if __name__ == "__main__":
    main()
