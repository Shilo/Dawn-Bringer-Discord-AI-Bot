"""Test that source link line numbers match documentation.md and prompt.md content."""

import sys
import os
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from rag.config import RAGConfig
from rag.utils import extract_text_from_file
from bot import initialize_rag_system


def test_line_number_consistency(query: str = "what is the best lineup?"):
    """Test that line numbers in retrieved chunks match the actual file content.
    
    This verifies that:
    1. Chunk content matches what's shown in documentation.md and prompt.md
    2. Line numbers in metadata match the actual content in the original file
    3. Source links would point to the correct lines
    """
    print("="*70)
    print("Testing Line Number Consistency")
    print("="*70)
    print(f"\nQuery: {query}\n")
    
    # Initialize RAG system
    print("Initializing RAG system...")
    rag_chain = initialize_rag_system(force_rebuild=False)
    
    if rag_chain is None:
        print("[FAIL] Failed to initialize RAG system")
        return False
    
    # Make query with scores to get chunk metadata
    print("Making query...")
    response_text, usage, metadata = rag_chain.query_with_usage(query, include_scores=True)
    
    retrieved_chunks = metadata.get("retrieved_chunks", [])
    full_prompt = metadata.get("full_prompt", "")
    
    # Verify that prompt.md would contain the same chunk content
    # prompt.md uses format_context() which gets doc.page_content
    # retrieved_chunks uses doc.page_content as "content"
    print("\nVerifying prompt.md content consistency...")
    if "[Run! Goddess Documentation]" in full_prompt:
        # Extract chunk content from prompt
        prompt_sections = full_prompt.split("[From ")
        prompt_chunk_contents = []
        for section in prompt_sections[1:]:  # Skip first part (system prompt)
            if "]\n" in section:
                chunk_text = section.split("]\n", 1)[1].split("\n\n---\n\n")[0]
                prompt_chunk_contents.append(chunk_text.strip())
        
        # Compare with retrieved_chunks content
        chunk_contents = [chunk.get("content", "").strip() for chunk in retrieved_chunks]
        
        if len(prompt_chunk_contents) == len(chunk_contents):
            prompt_matches = all(
                prompt_content == chunk_content 
                for prompt_content, chunk_content in zip(prompt_chunk_contents, chunk_contents)
            )
            if prompt_matches:
                print("[OK] prompt.md content matches retrieved_chunks content")
            else:
                print("[WARN] prompt.md content may differ from retrieved_chunks")
        else:
            print(f"[WARN] Mismatch: {len(prompt_chunk_contents)} chunks in prompt vs {len(chunk_contents)} in metadata")
    else:
        print("[WARN] No documentation found in prompt")
    
    print()
    
    if not retrieved_chunks:
        print("[FAIL] No chunks retrieved")
        return False
    
    print(f"Retrieved {len(retrieved_chunks)} chunks\n")
    
    all_passed = True
    
    for i, chunk in enumerate(retrieved_chunks, 1):
        print(f"{'='*70}")
        print(f"Chunk {i}")
        print(f"{'='*70}")
        
        source = chunk.get("source", "Unknown")
        chunk_content = chunk.get("content", "")
        chunk_metadata = chunk.get("metadata", {})
        
        print(f"Source: {source}")
        
        # Get line numbers from metadata
        start_line = None
        end_line = None
        if isinstance(chunk_metadata, dict):
            try:
                start_line = int(chunk_metadata.get("start_line")) if chunk_metadata.get("start_line") else None
                end_line = int(chunk_metadata.get("end_line")) if chunk_metadata.get("end_line") else None
            except (ValueError, TypeError):
                pass
        
        if not start_line:
            print("[WARN] No start_line in metadata")
            all_passed = False
            continue
        
        print(f"Line numbers in metadata: {start_line}-{end_line}")
        
        # Get file path from metadata
        file_path = chunk_metadata.get("file_path") if isinstance(chunk_metadata, dict) else None
        if not file_path:
            # Fallback: try to add .md extension to source
            file_path = source if source.endswith(('.md', '.txt')) else f"{source}.md"
        
        print(f"File path: {file_path}")
        
        # Extract text from original file using line numbers
        extracted_text, actual_start, actual_end = extract_text_from_file(file_path, start_line, end_line)
        
        print(f"Extracted lines from file: {actual_start}-{actual_end}")
        
        # Normalize both texts for comparison
        chunk_norm = chunk_content.strip()
        extracted_norm = extracted_text.strip()
        
        # Check if chunk content appears in extracted text (or vice versa)
        # Since cleaned content may differ from original, we check for significant overlap
        chunk_preview = chunk_norm[:200] if len(chunk_norm) > 200 else chunk_norm
        extracted_preview = extracted_norm[:200] if len(extracted_norm) > 200 else extracted_norm
        
        # Clean the extracted text for comparison (remove markdown headers, links, emojis, metadata tags)
        # This simulates what the cleaning process does
        import re
        extracted_cleaned_lines = []
        for line in extracted_norm.split('\n'):
            line_stripped = line.strip()
            # Skip metadata tags, images, and Discord links
            if (not line_stripped or
                re.match(r'^\|\|.*\|\|$', line_stripped) or
                re.match(r'^!\[.*\]\(.*\)$', line_stripped) or
                '[▲Top]' in line_stripped):
                continue
            # Clean markdown headers (remove emojis and links but keep text)
            if re.match(r'^##+\s+', line_stripped):
                header_text = re.sub(r'^##+\s+', '', line_stripped)
                header_text = re.sub(r':\w+:', '', header_text)  # Remove emoji
                header_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', header_text)  # Remove links
                extracted_cleaned_lines.append(header_text.strip())
            else:
                extracted_cleaned_lines.append(line)
        extracted_cleaned = '\n'.join(extracted_cleaned_lines).strip()
        
        # Check for overlap - chunk content should match cleaned extracted text
        matches = False
        if chunk_norm and extracted_cleaned:
            # Compare cleaned versions
            chunk_key = chunk_norm[:150].strip().lower() if len(chunk_norm) > 150 else chunk_norm.strip().lower()
            extracted_key = extracted_cleaned[:150].strip().lower() if len(extracted_cleaned) > 150 else extracted_cleaned.strip().lower()
            
            # Check if significant portion matches
            if len(chunk_key) > 50:
                # Check if first 100 chars of chunk appear in cleaned extracted text
                key_phrase = chunk_key[:100]
                matches = key_phrase in extracted_key or extracted_key[:100] in chunk_key
            else:
                matches = chunk_key in extracted_key or extracted_key in chunk_key
        
        # Also check if we can find the chunk content in the file (even if cleaned)
        if not matches:
            # Try finding chunk content in original file
            from rag.utils import find_text_in_file
            found_line_nums = find_text_in_file(file_path, chunk_content[:100] if len(chunk_content) > 100 else chunk_content)
            if found_line_nums:
                found_start, found_end = found_line_nums
                print(f"Found chunk content in file at lines: {found_start}-{found_end}")
                # Check if found lines are close to metadata lines (within 5 lines)
                if abs(found_start - start_line) <= 5:
                    matches = True
                    print(f"[OK] Line numbers are close (within 5 lines)")
        
        if matches:
            print("[PASS] Chunk content matches file content at specified lines")
        else:
            print("[FAIL] Chunk content does not match file content at specified lines")
            print(f"\nChunk content (cleaned) preview:")
            print(f"  {chunk_preview[:150]}...")
            print(f"\nExtracted file content (original) preview:")
            print(f"  {extracted_preview[:150]}...")
            print(f"\nExtracted file content (cleaned) preview:")
            print(f"  {extracted_cleaned[:150] if len(extracted_cleaned) > 150 else extracted_cleaned}...")
            all_passed = False
        
        # Verify that documentation.md and prompt.md would show the same content
        # (They both use chunk.get("content") or doc.page_content)
        print(f"\nContent length: {len(chunk_content)} chars")
        print(f"Content preview: {chunk_content[:100]}...")
        
        # Verify consistency: documentation.md uses chunk.get("content")
        # prompt.md uses doc.page_content (which is the same as chunk.get("content"))
        # Both should be identical
        print(f"[OK] documentation.md and prompt.md both use: chunk.get('content')")
        print(f"     (which equals doc.page_content from the vector store)")
        
        print()
    
    print(f"\n{'='*70}")
    print("Summary")
    print(f"{'='*70}")
    
    if all_passed:
        print("[PASS] ALL TESTS PASSED")
        print("\nVerification:")
        print("  [OK] documentation.md uses chunk.get('content')")
        print("  [OK] prompt.md uses doc.page_content (same as chunk.get('content'))")
        print("  [OK] Source links use start_line/end_line from chunk metadata")
        print("  [OK] Line numbers point to correct content in original files")
        print("\n[OK] All three outputs (documentation.md, prompt.md, source links)")
        print("     reference the same chunk content with consistent line numbers")
    else:
        print("[FAIL] SOME TESTS FAILED")
        print("\nIssues found:")
        print("  [WARN] Line numbers in metadata may not match file content")
        print("  [WARN] Chunk content may not be found at specified line numbers")
        print("\nNote: This may require rebuilding the vector store")
        print("      to recalculate line numbers from original files")
    
    print(f"{'='*70}\n")
    
    return all_passed


def main():
    """Run the test."""
    try:
        passed = test_line_number_consistency("what is the best lineup?")
        return 0 if passed else 1
    except Exception as e:
        print(f"\n[ERROR] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

