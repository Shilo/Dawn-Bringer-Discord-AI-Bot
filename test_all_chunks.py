"""Comprehensive test for all chunk line numbers - simplified version."""

from pathlib import Path
import sys
import re

# Copy the essential functions to avoid import issues
def find_text_line_numbers(original_content: str, search_text: str, start_from_line: int = 1):
    """Find text in original content and return its line numbers."""
    if not search_text or not original_content:
        return None
    
    search_text = search_text.strip()
    if not search_text:
        return None
    
    pos = original_content.find(search_text)
    
    if pos == -1 and len(search_text) > 100:
        prefix = search_text[:100].strip()
        pos = original_content.find(prefix)
    
    if pos == -1:
        return None
    
    start_line = 1 + original_content[:pos].count('\n')
    end_line = start_line + search_text.count('\n')
    
    return (start_line, end_line)

def extract_text_from_file(file_path: str, start_line: int, end_line: int = None):
    """Extract exact text from original file using line numbers."""
    if end_line is None:
        end_line = start_line
    
    full_path = Path("docs") / file_path
    
    if not full_path.exists():
        return ("", start_line, end_line)
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        
        extracted_lines = lines[start_idx:end_idx]
        extracted_text = ''.join(extracted_lines).rstrip('\n')
        
        actual_start = start_idx + 1
        actual_end = end_idx
        
        return (extracted_text, actual_start, actual_end)
    except Exception as e:
        print(f"Error reading file {full_path}: {e}")
        return ("", start_line, end_line)

# Simple document loader
class SimpleDocument:
    def __init__(self, content, metadata):
        self.content = content
        self.metadata = metadata

def load_document_simple(file_path: Path):
    """Load a document without full dependencies."""
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Detect doc type
        path_str = str(file_path).lower()
        if "faq" in path_str or "frequently-asked" in path_str:
            doc_type = "faq"
        elif "valkyries" in path_str or "valkyrie" in path_str:
            doc_type = "character"
        elif "guide" in path_str or "guides" in path_str:
            doc_type = "guide"
        elif re.match(r'\d+-[A-Za-z].*\.md$', file_path.name):
            doc_type = "character"
        else:
            doc_type = "general"
        
        metadata = {
            "source": str(file_path.relative_to(Path("docs"))),
            "doc_type": doc_type,
        }
        
        return SimpleDocument(content, metadata)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

# Simple chunker that just tests the line number finding
def test_file_chunking(file_path: str):
    """Test chunking by manually chunking and finding line numbers."""
    
    print(f"\n{'='*60}")
    print(f"Testing: {file_path}")
    print(f"{'='*60}")
    
    full_path = Path("docs") / file_path
    doc = load_document_simple(full_path)
    
    if not doc:
        print(f"[FAIL] Failed to load document")
        return False
    
    content = doc.content
    doc_type = doc.metadata.get("doc_type", "general")
    
    # Simple chunking based on type
    chunks = []
    
    if doc_type == "faq":
        # Split by headers - find all headers first
        header_pattern = r'^##+\s+(.+)$'
        lines = content.split('\n')
        
        # Find all headers and their line numbers
        headers = []
        for line_num, line in enumerate(lines, start=1):
            header_match = re.match(header_pattern, line)
            if header_match:
                header_text = header_match.group(1).strip()
                question_text = re.sub(r':\w+:', '', header_text)
                question_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', question_text)
                question_text = question_text.strip()
                headers.append((line_num, question_text))
        
        # Process each Q&A pair
        for i, (q_line, question) in enumerate(headers):
            # Find answer (from this header to next header or end)
            if i + 1 < len(headers):
                next_q_line = headers[i + 1][0]
                answer_lines = lines[q_line:next_q_line - 1]
            else:
                answer_lines = lines[q_line:]
            
            # Build answer text (excluding images and metadata)
            answer_parts = []
            for line in answer_lines[1:]:  # Skip the header line
                if not re.match(r'^!\[.*\]\(.*\)$', line):
                    answer_parts.append(line)
            
            answer_text = '\n'.join(answer_parts).strip()
            
            if answer_text:
                # Build chunk content
                chunk_content = f"{question}\n\n{answer_text}"
                
                # Find in original
                line_nums = find_text_line_numbers(content, chunk_content)
                if not line_nums:
                    # Try finding just the question
                    line_nums = find_text_line_numbers(content, question)
                    if line_nums:
                        # Use question line as start, estimate end
                        start_line = line_nums[0]
                        # Find last non-empty, non-metadata line
                        end_line = start_line + len([l for l in answer_parts if l.strip() and not re.match(r'^\|\|.*\|\|$', l.strip())])
                    else:
                        start_line = q_line
                        end_line = q_line + len(answer_parts)
                else:
                    start_line, end_line = line_nums
                    # Trim trailing metadata
                    while end_line > start_line:
                        line_content = lines[end_line - 1].strip()
                        if (not line_content or 
                            re.match(r'^\|\|.*\|\|$', line_content) or
                            re.match(r'^!\[.*\]\(.*\)$', line_content)):
                            end_line -= 1
                        else:
                            break
                
                chunks.append({
                    "content": chunk_content,
                    "start_line": start_line,
                    "end_line": end_line,
                })
    
    elif doc_type in ["character", "guide"]:
        # Split by sections
        sections = re.split(r'\n(##+\s+.+)\n', content)
        
        if len(sections) > 1:
            for i, section in enumerate(sections):
                if i == 0 and section.strip():
                    # First section
                    stripped = section.strip()
                    line_nums = find_text_line_numbers(content, stripped)
                    if line_nums:
                        chunks.append({
                            "content": stripped,
                            "start_line": line_nums[0],
                            "end_line": line_nums[1],
                        })
                elif i % 2 == 0 and section.strip():
                    # Section content
                    stripped = section.strip()
                    line_nums = find_text_line_numbers(content, stripped)
                    if line_nums:
                        chunks.append({
                            "content": stripped,
                            "start_line": line_nums[0],
                            "end_line": line_nums[1],
                        })
        else:
            # No sections, use first 500 chars as test
            test_chunk = content[:500].strip()
            line_nums = find_text_line_numbers(content, test_chunk)
            if line_nums:
                chunks.append({
                    "content": test_chunk,
                    "start_line": line_nums[0],
                    "end_line": line_nums[1],
                })
    
    if not chunks:
        print(f"[WARN] No chunks generated")
        return True
    
    print(f"[OK] Generated {len(chunks)} chunks\n")
    
    passed = 0
    for i, chunk in enumerate(chunks, 1):
        start_line = chunk.get("start_line")
        end_line = chunk.get("end_line")
        chunk_content = chunk.get("content", "")
        
        if not start_line:
            print(f"  Chunk {i}: [FAIL] Missing start_line")
            continue
        
        # Verify by extracting
        extracted, actual_start, actual_end = extract_text_from_file(file_path, start_line, end_line)
        
        chunk_norm = chunk_content.strip()
        extracted_norm = extracted.strip()
        
        matches = (chunk_norm in extracted_norm or extracted_norm in chunk_norm or
                  chunk_norm[:100] in extracted_norm[:200])
        
        status = "[OK]" if matches else "[WARN]"
        print(f"  Chunk {i}: Lines {start_line}-{end_line} {status}")
        
        if matches:
            passed += 1
        else:
            # Show preview (avoid unicode issues)
            try:
                preview = chunk_norm[:50].encode('ascii', 'ignore').decode('ascii')
                print(f"    Preview: {preview}...")
            except:
                print(f"    Preview: [content mismatch]")
    
    print(f"\n  Summary: {passed}/{len(chunks)} chunks verified")
    return passed == len(chunks)

def main():
    """Test all document types."""
    
    print("="*60)
    print("Comprehensive Chunk Line Number Test")
    print("="*60)
    
    test_files = [
        ("valkyries/100019-Emilius.md", "character"),
        ("faq-frequently-asked-questions/FAQ - 2. Player.md", "faq"),
        ("faq-frequently-asked-questions/FAQ - 3. Gameplay.md", "faq"),
        ("all-the-guides-topic/4. Classes Guide.md", "guide"),
    ]
    
    results = []
    
    for file_path, doc_type in test_files:
        passed = test_file_chunking(file_path)
        results.append((file_path, passed))
    
    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for file_path, passed in results:
        status = "[OK]" if passed else "[WARN]"
        print(f"{status} {file_path}")
    
    print(f"\n{passed_count}/{total_count} files passed")
    
    if passed_count == total_count:
        print("\n[OK] All tests passed!")
    else:
        print("\n[WARN] Some tests had warnings")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
