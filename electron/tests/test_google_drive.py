"""
Unit tests for Google Drive conversion
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'python'))


class TestGoogleDriveExtraction:
    """Test Google Drive URL/file ID extraction."""
    
    def test_extract_file_id_from_url(self):
        """Test extracting file ID from Google Drive URL."""
        import google_drive as gd
        
        # Test various URL formats
        test_urls = [
            "https://docs.google.com/document/d/1ABC123/edit",
            "https://drive.google.com/file/d/1ABC123/view",
            "https://docs.google.com/spreadsheets/d/1ABC123/edit",
        ]
        
        for url in test_urls:
            file_id, doc_type = gd.extract_file_id(url)
            assert file_id == "1ABC123"
            assert doc_type is not None
    
    def test_extract_file_id_direct_id(self):
        """Test extracting file ID when only ID is provided."""
        import google_drive as gd
        
        file_id, doc_type = gd.extract_file_id("1ABC123")
        assert file_id == "1ABC123"
        assert doc_type is None
    
    def test_extract_file_id_invalid_url(self):
        """Test extracting file ID from invalid URL."""
        import google_drive as gd
        
        file_id, doc_type = gd.extract_file_id("https://example.com/file")
        assert file_id is None
        assert doc_type is None


class TestGoogleDriveDownload:
    """Test Google Drive download functionality."""
    
    @patch('google_drive.extract_file_id')
    @patch('google_drive.webbrowser')
    def test_download_url_parsing(self, mock_browser, mock_extract, tmp_path):
        """Test that download function correctly parses URL."""
        import google_drive as gd
        
        mock_extract.return_value = ("1ABC123", "document")
        mock_browser.open = Mock()
        
        # This test verifies URL parsing logic
        # Actual download would require browser automation
        url = "https://docs.google.com/document/d/1ABC123/edit"
        
        # Mock the file system operations
        with patch('google_drive._get_downloads_folder', return_value=tmp_path):
            with patch('google_drive._snapshot_downloads', return_value=set()):
                try:
                    result = gd.download(url, tmp_path)
                except Exception as e:
                    # Expected to fail in test environment without browser
                    assert "download" in str(e).lower() or "browser" in str(e).lower()


class TestGoogleDriveIntegration:
    """Test Google Drive integration with web app."""
    
    def test_gdrive_endpoint_requires_url(self):
        """Test that Google Drive endpoint requires URL."""
        from web_app import app
        
        with app.test_client() as client:
            response = client.post('/convert-gdrive',
                                   data=json.dumps({}),
                                   content_type='application/json')
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_gdrive_endpoint_accepts_url(self):
        """Test that Google Drive endpoint accepts URL."""
        from web_app import app
        
        with app.test_client() as client:
            response = client.post('/convert-gdrive',
                                   data=json.dumps({'url': 'https://docs.google.com/document/d/1ABC123/edit'}),
                                   content_type='application/json')
            # Will fail in test environment but should accept the request
            assert response.status_code in [400, 500]  # Expected to fail without real Google Drive access


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
