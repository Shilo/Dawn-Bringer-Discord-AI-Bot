#!/usr/bin/env python3
"""
Test script for share page meta tag generation.

Usage:
    python test_share_meta.py                    # Run with default test data
    python test_share_meta.py <share_url>        # Test with actual share URL
"""

import sys
import argparse
from pathlib import Path

def parse_share_id_from_url(url):
    """Parse share ID from a share URL or return the ID if it's already just the ID.

    Args:
        url: Share URL like 'https://rgai.up.railway.app/YhJb3f' or just 'YhJb3f'

    Returns:
        str: The 6-character share ID, or None if invalid
    """
    if not url:
        return None

    # If it's already just a 6-character alphanumeric string, return it
    url = url.strip()
    if len(url) == 6 and url.isalnum():
        return url

    try:
        # Remove protocol and domain
        if '://' in url:
            url = url.split('://', 1)[1]

        # Remove domain part
        if '/' in url:
            path = url.split('/', 1)[1]
        else:
            return None

        # Remove leading/trailing slashes and get the last part
        share_id = path.strip('/').split('/')[-1]

        # Validate it's a 6-character alphanumeric string
        if len(share_id) == 6 and share_id.isalnum():
            return share_id
        else:
            return None
    except:
        return None

def test_meta_tag_replacement(share_url=None):
    """Test the HTML meta tag replacement logic directly."""

    # Original HTML template
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dawn Bringer - Run! Goddess AI</title>
    <link rel="icon" type="image/png" href="/static/icon.png">
    <link rel="stylesheet" href="/static/style.css">
    <script src="https://cdn.jsdelivr.net/npm/marked@11.1.1/marked.min.js"></script>

    <!-- Open Graph / Discord Preview Meta Tags -->
    <meta property="og:title" content="Dawn Bringer - Run! Goddess AI">
    <meta property="og:description" content="Ask anything about Run! Goddess - Your AI companion">
    <meta property="og:image" content="/static/icon.png">
    <meta property="og:url" content="/">
    <meta property="og:type" content="website">

    <!-- Twitter Card Meta Tags -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Dawn Bringer - Run! Goddess AI">
    <meta name="twitter:description" content="Ask anything about Run! Goddess - Your AI companion">
    <meta name="twitter:image" content="/static/icon.png">
</head>
<body>
    <div class="container">
        Test content
    </div>
    <script src="/static/script.js"></script>
</body>
</html>"""

    # Default test data
    question = 'What is the best Valkyrie to use?'
    answer = 'The best Valkyrie depends on your playstyle and the situation. For beginners, I recommend starting with Dawn Bringer herself - she\'s versatile and powerful in most scenarios.'
    test_share_id = 'test123'
    test_base_url = 'https://example.railway.app'
    final_share_url = f'{test_base_url}/{test_share_id}'

    # If a share URL was provided, try to parse it and get real data
    if share_url:
        share_id = parse_share_id_from_url(share_url)
        if share_id:
            print(f"Parsed share ID from URL: {share_id}")

            # Try to get real share data (this will only work if the bot is running and has the data)
            try:
                # Add parent directory to path so we can import modules
                sys.path.insert(0, str(Path(__file__).parent.parent))

                # Try to import and get real share data
                import share_db

                # Try to get the share data
                share_data = share_db.get_share(share_id)
                if share_data:
                    print("Found real share data!")
                    question = share_data['prompt']
                    answer = share_data['response']

                    # Use the provided URL as the base for og:url
                    if '://' in share_url:
                        url_parts = share_url.split('/')
                        final_share_url = '/'.join(url_parts[:3]) + '/' + share_id
                    else:
                        final_share_url = share_url
                else:
                    print("Share not found in database, using test data")
            except Exception as e:
                print(f"Could not load real share data ({e}), using test data")
        else:
            print(f"Could not parse share ID from URL: {share_url}")
            print("Using test data instead")

    print(f"Testing with:")
    print(f"  Question: {question}")
    print(f"  Answer: {answer[:100]}{'...' if len(answer) > 100 else ''}")
    print(f"  Share URL: {final_share_url}")
    print()

    # HTML escaping
    question_escaped = question.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    answer_escaped = answer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # Apply the same replacements as in web_server.py
    html_content = html_template
    html_content = html_content.replace(
        '<meta property="og:title" content="Dawn Bringer - Run! Goddess AI">',
        f'<meta property="og:title" content="{question_escaped}">'
    )
    html_content = html_content.replace(
        '<meta property="og:description" content="Ask anything about Run! Goddess - Your AI companion">',
        f'<meta property="og:description" content="{answer_escaped}">'
    )
    html_content = html_content.replace(
        '<meta property="og:url" content="/">',
        f'<meta property="og:url" content="{final_share_url}">'
    )

    # Twitter Card meta tags
    html_content = html_content.replace(
        '<meta name="twitter:title" content="Dawn Bringer - Run! Goddess AI">',
        f'<meta name="twitter:title" content="{question_escaped}">'
    )
    html_content = html_content.replace(
        '<meta name="twitter:description" content="Ask anything about Run! Goddess - Your AI companion">',
        f'<meta name="twitter:description" content="{answer_escaped}">'
    )

    # Page title
    html_content = html_content.replace(
        '<title>Dawn Bringer - Run! Goddess AI</title>',
        f'<title>{question_escaped} - Dawn Bringer</title>'
    )

    # Test the replacements
    print("Testing HTML meta tag replacement...")

    # Check that meta tags were replaced
    assert f'property="og:title" content="{question_escaped}"' in html_content, "og:title not updated"
    assert f'property="og:description" content="{answer_escaped}"' in html_content, "og:description not updated"
    assert f'property="og:url" content="{final_share_url}"' in html_content, "og:url not updated"

    # Check Twitter meta tags
    assert f'name="twitter:title" content="{question_escaped}"' in html_content, "twitter:title not updated"
    assert f'name="twitter:description" content="{answer_escaped}"' in html_content, "twitter:description not updated"

    # Check page title
    assert f'<title>{question_escaped} - Dawn Bringer</title>' in html_content, "Page title not updated"

    print("All HTML replacement tests passed!")
    print(f"Question: {question}")
    print(f"Answer preview: {answer[:100]}{'...' if len(answer) > 100 else ''}")
    print(f"Share URL: {final_share_url}")

def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Test share page meta tag generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_share_meta.py
    Run with default test data

  python test_share_meta.py https://rgai.up.railway.app/YhJb3f
    Test with actual share URL (will try to load real data)

  python test_share_meta.py YhJb3f
    Test with just the share ID
        """
    )
    parser.add_argument(
        'share_url',
        nargs='?',
        help='Share URL or share ID to test with (optional)'
    )

    args = parser.parse_args()

    try:
        test_meta_tag_replacement(args.share_url)
        print("\nAll tests completed successfully!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()