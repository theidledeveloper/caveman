#!/usr/bin/env python3
"""Caveman Compress CLI."""

import sys
from pathlib import Path

from .compress import compress_file
from .detect import detect_file_type, should_compress
from .targets import resolve_targets


def print_usage():
    print("Usage: caveman <filepath|pattern|list> [more paths/patterns ...]")
    print("Examples:")
    print("  caveman /abs/path/to/CLAUDE.md")
    print("  caveman /abs/path/to/CLAUDE.md /abs/path/to/GEMINI.md")
    print('  caveman "[\'/abs/path/to/CLAUDE.md\', \'/abs/path/to/GEMINI.md\']"')
    print('  caveman "/abs/path/to/docs/**/*.md"')


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    resolution = resolve_targets(sys.argv[1:], cwd=Path.cwd())

    for target in resolution.unmatched:
        print(f"⚠️ No files matched: {target}")

    if not resolution.files:
        print("❌ No files to process")
        sys.exit(1)

    print(f"Resolved {len(resolution.files)} file(s)")

    success_count = 0
    skip_count = 0
    failure_count = 0

    for filepath in resolution.files:
        file_type = detect_file_type(filepath)
        print(f"\nDetected: {file_type}")
        print(f"Target:   {filepath}")

        if not should_compress(filepath):
            print("Skipping: file is not natural language (code/config)")
            skip_count += 1
            continue

        print("Starting caveman compression...\n")

        try:
            success = compress_file(filepath)
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            sys.exit(130)
        except Exception as exc:
            print(f"\n❌ Error: {exc}")
            failure_count += 1
            continue

        if success:
            success_count += 1
            print("\nCompression completed successfully")
            backup_path = filepath.with_name(filepath.stem + ".original.md")
            print(f"Compressed: {filepath}")
            print(f"Original:   {backup_path}")
        else:
            failure_count += 1
            print("\n❌ Compression failed after retries")

    print(
        "\nSummary:"
        f" success={success_count}"
        f" skipped={skip_count}"
        f" failed={failure_count}"
        f" unmatched={len(resolution.unmatched)}"
    )

    if failure_count or resolution.unmatched:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
