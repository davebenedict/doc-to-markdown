"""
Unit tests for token stats calculation
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'python'))

import converter as conv


class TestTokenStats:
    """Test token statistics calculation."""
    
    def test_token_stats_basic(self, tmp_path):
        """Test basic token stats calculation."""
        # Create a simple markdown file
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nThis is a test document.")
        
        src_text = "This is the source text content."
        stats = conv.token_stats(src_text, md_file)
        
        assert 'tiktoken_available' in stats
        assert 'src_tokens' in stats
        assert 'out_tokens' in stats
        assert 'savings_pct' in stats
        assert 'method' in stats
    
    def test_token_stats_with_source_file(self, tmp_path):
        """Test token stats with source file."""
        # Create source and output files
        src_file = tmp_path / "source.txt"
        src_file.write_text("Source content here")
        
        md_file = tmp_path / "output.md"
        md_file.write_text("# Markdown output")
        
        src_text = src_file.read_text()
        stats = conv.token_stats(src_text, md_file, src=src_file)
        
        assert stats['src_tokens'] > 0
        assert stats['out_tokens'] > 0
    
    def test_token_stats_empty_content(self, tmp_path):
        """Test token stats with empty content."""
        md_file = tmp_path / "empty.md"
        md_file.write_text("")
        
        stats = conv.token_stats("", md_file)
        
        assert stats['src_tokens'] == 0
        assert stats['out_tokens'] == 0
    
    def test_token_stats_large_document(self, tmp_path):
        """Test token stats with larger document."""
        md_file = tmp_path / "large.md"
        large_content = "# Title\n\n" + "This is a paragraph. " * 100
        md_file.write_text(large_content)
        
        src_text = "Source text " * 100
        stats = conv.token_stats(src_text, md_file)
        
        assert stats['src_tokens'] > stats['out_tokens']


class TestTokenCounting:
    """Test individual token counting functions."""
    
    def test_count_tokens_approx(self):
        """Test approximate token counting."""
        text = "This is a test document."
        tokens = conv._count_tokens_approx(text)
        assert tokens > 0
        assert tokens < len(text)  # Should be less than character count
    
    def test_count_tokens_approx_empty(self):
        """Test approximate token counting with empty string."""
        tokens = conv._count_tokens_approx("")
        assert tokens == 0
    
    def test_count_tokens_approx_large(self):
        """Test approximate token counting with large text."""
        text = "This is a test. " * 1000
        tokens = conv._count_tokens_approx(text)
        assert tokens > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
