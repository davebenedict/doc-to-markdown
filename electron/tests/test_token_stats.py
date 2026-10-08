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
        
        assert stats['src_tokens'] > 0
        assert stats['out_tokens'] > 0


class TestTokenCounting:
    """Test token counting with and without tiktoken."""

    def test_count_tokens(self):
        text = "This is a test document."
        tokens = conv._count_tokens(text)
        expected = len(conv._enc.encode(text)) if conv.TIKTOKEN_AVAILABLE else len(text) // 4
        assert tokens == expected

    def test_count_tokens_empty(self):
        assert conv._count_tokens("") == 0

    def test_count_tokens_large(self):
        text = "This is a test. " * 1000
        assert conv._count_tokens(text) > 0


class TestFriendlyErrorMessages:
    def test_missing_python_package_suggests_requirements(self):
        exc = ImportError("Required package 'PyMuPDF' is not installed.")
        message = conv.friendly_error_message(exc)
        assert "PyMuPDF" in message
        assert str(Path(conv.__file__).with_name("requirements.txt")) in message

    def test_missing_tesseract_suggests_install_and_path(self):
        exc = type("TesseractNotFoundError", (Exception,), {})()
        message = conv.friendly_error_message(exc)
        assert "Tesseract" in message
        assert "PATH" in message

    def test_permission_error_suggests_writable_folder(self):
        message = conv.friendly_error_message(PermissionError("access denied"))
        assert "write permission" in message


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
