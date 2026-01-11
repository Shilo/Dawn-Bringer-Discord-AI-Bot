#!/usr/bin/env python3
"""
Script to clear cached preview images for specific shares.

This forces regeneration of Discord preview images with updated fonts/rendering.
"""

import sys
import share_db

def main():
    if len(sys.argv) < 2:
        print("Usage: python clear_preview_cache.py <short_id> [short_id2] ...")
        print("Example: python clear_preview_cache.py Hxps8U")
        return

    for short_id in sys.argv[1:]:
        if share_db.clear_preview_image(short_id):
            print(f"✅ Cleared preview cache for share: {short_id}")
        else:
            print(f"❌ Failed to clear preview cache for share: {short_id}")

if __name__ == "__main__":
    main()