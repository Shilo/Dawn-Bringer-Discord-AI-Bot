#!/usr/bin/env python3
"""
Script to clear cached preview images for specific shares or all shares.

This forces regeneration of Discord preview images with updated fonts/rendering.
"""

import sys
import share_db


def clear_all_preview_cache():
    """Clear cached preview images for all shares.

    Returns:
        int: Number of caches cleared
    """
    conn = share_db.get_db_connection()

    try:
        cursor = conn.execute(
            """
            UPDATE shares
            SET preview_image = NULL, preview_generated_at = NULL
            WHERE preview_image IS NOT NULL
        """
        )

        cleared_count = cursor.rowcount
        conn.commit()

        print(f"[SUCCESS] Cleared preview cache for {cleared_count} shares")
        return cleared_count

    except Exception as e:
        print(f"[ERROR] Error clearing all cache: {e}")
        return 0
    finally:
        conn.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python clear_preview_cache.py <short_id> [short_id2] ...")
        print("       python clear_preview_cache.py --all")
        print()
        print("Examples:")
        print("  python clear_preview_cache.py Hxps8U SZDhZ8  # Clear specific shares")
        print("  python clear_preview_cache.py --all         # Clear all cached images")
        return

    if sys.argv[1] == "--all":
        # Clear all cached preview images
        clear_all_preview_cache()
    else:
        # Clear specific share caches
        for short_id in sys.argv[1:]:
            if share_db.clear_preview_image(short_id):
                print(f"[SUCCESS] Cleared preview cache for share: {short_id}")
            else:
                print(f"[FAILED] Failed to clear preview cache for share: {short_id}")


if __name__ == "__main__":
    main()
