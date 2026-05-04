#!/usr/bin/env python3
"""
scripts/filter_yt_cookies.py — Strip a full browser cookies.txt export down to
only the essential YouTube authentication cookies.

Full exports from browser extensions can be 200 KB+ (tracking pixels, A/B test
flags, etc.) which exceeds GitHub Secrets' 64 KB limit.  This script keeps only
the ~15 cookies that yt-dlp actually needs to authenticate and outputs a clean
Netscape-format file that is typically < 5 KB.

Usage:
    python scripts/filter_yt_cookies.py cookies.txt
    python scripts/filter_yt_cookies.py cookies.txt --out yt_cookies_slim.txt

Then base64-encode the output and store it as YOUTUBE_COOKIES_B64:
    PowerShell:
        [Convert]::ToBase64String([IO.File]::ReadAllBytes("yt_cookies_slim.txt")) | Set-Clipboard
"""

import argparse
import sys
from pathlib import Path

# The only cookies yt-dlp needs to authenticate with YouTube.
# Everything else (analytics, A/B experiments, ad targeting…) can be dropped.
ESSENTIAL_COOKIE_NAMES = {
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "LOGIN_INFO",
    "SIDCC",
    "PREF",
    "VISITOR_INFO1_LIVE",
    "YSC",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "__Secure-1PSIDCC",
    "__Secure-3PSIDCC",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
}

YOUTUBE_DOMAINS = {".youtube.com", "youtube.com", ".google.com", "google.com"}


def filter_cookies(input_path: Path, output_path: Path) -> int:
    """
    Read a Netscape cookies.txt, keep only essential YouTube auth cookies,
    write the result to output_path.  Returns the number of lines kept.
    """
    kept_lines = []
    total = 0
    kept = 0

    with input_path.open(encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")

            # Pass through the header comment block unchanged.
            if line.startswith("#"):
                kept_lines.append(line)
                continue

            if not line.strip():
                continue  # skip blank lines

            parts = line.split("\t")
            if len(parts) < 7:
                continue  # malformed — skip

            total += 1
            domain = parts[0].strip()
            name   = parts[5].strip()

            # Keep only essential named cookies on YouTube/Google domains.
            if domain in YOUTUBE_DOMAINS and name in ESSENTIAL_COOKIE_NAMES:
                kept_lines.append(line)
                kept += 1

    output_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    return kept, total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter a browser cookies.txt to only essential YouTube auth cookies.",
    )
    parser.add_argument("input", help="Path to the full cookies.txt export from your browser.")
    parser.add_argument(
        "--out",
        default="yt_cookies_slim.txt",
        help="Output file path (default: yt_cookies_slim.txt)",
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.out)

    if not input_path.exists():
        print(f"❌  File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    kept, total = filter_cookies(input_path, output_path)
    size_kb = output_path.stat().st_size / 1024

    print(f"✅  Done — kept {kept}/{total} cookies → {output_path}  ({size_kb:.1f} KB)")

    if size_kb > 60:
        print(
            f"⚠️   Output is {size_kb:.1f} KB — still close to the 64 KB GitHub secret limit.\n"
            "    Check for unexpected large cookie values in the output file."
        )
    else:
        print("   File is within GitHub Secrets' 64 KB limit — safe to base64-encode and upload.")

    print()
    print("Next step — copy base64 to clipboard (PowerShell):")
    print(f'  [Convert]::ToBase64String([IO.File]::ReadAllBytes("{output_path}")) | Set-Clipboard')


if __name__ == "__main__":
    main()
