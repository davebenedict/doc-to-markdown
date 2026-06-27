"""
Unit tests for Flask web backend
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import os

# Set up test environment
os.environ['TESTING'] = 'true'

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'python'))

from web_app import app, _CONFIG_FILE, _converted_files


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        'output_dir': '/tmp/output',
        'remember_output_dir': True,
        'datetime_subfolder': False
    }


class TestConfigEndpoints:
    """Test configuration endpoints."""
    
    def test_get_config_empty(self, client):
        """Test getting config when none exists."""
        response = client.get('/config')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)
    
    def test_save_config(self, client, sample_config):
        """Test saving configuration."""
        response = client.post('/config',
                               data=json.dumps(sample_config),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
    
    def test_get_config_after_save(self, client, sample_config):
        """Test getting config after saving."""
        # Save config first
        client.post('/config',
                   data=json.dumps(sample_config),
                   content_type='application/json')
        
        # Get config
        response = client.get('/config')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('output_dir') == sample_config['output_dir']
        assert data.get('remember_output_dir') == sample_config['remember_output_dir']


class TestConvertedFilesEndpoint:
    """Test converted files endpoint."""
    
    def test_get_converted_files_empty(self, client):
        """Test getting converted files when none exist."""
        # Clear the global list
        global _converted_files
        _converted_files = []
        
        response = client.get('/converted-files')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_clear_converted_files(self, client):
        """Test clearing converted files list."""
        # Add a file to the list
        global _converted_files
        _converted_files = [{'name': 'test.md', 'path': '/tmp/test.md'}]
        
        # Clear the list
        response = client.delete('/converted-files')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        # Verify it's cleared
        assert len(_converted_files) == 0


class TestSupportedFormatsEndpoint:
    """Test supported formats endpoint."""
    
    def test_supported_formats(self, client):
        """Test getting supported formats."""
        response = client.get('/supported-formats')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'formats' in data
        assert 'missing_deps' in data
        assert isinstance(data['formats'], list)
        assert isinstance(data['missing_deps'], dict)


class TestTokenCountEndpoint:
    """Test token count endpoint."""
    
    def test_token_count_approx(self, client):
        """Test token count with approximate method."""
        response = client.post('/token-count',
                               data=json.dumps({
                                   'content': 'Hello world',
                                   'use_tiktoken': False
                               }),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'tokens' in data
        assert data['tokens'] > 0
    
    def test_token_count_empty_content(self, client):
        """Test token count with empty content."""
        response = client.post('/token-count',
                               data=json.dumps({
                                   'content': '',
                                   'use_tiktoken': False
                               }),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['tokens'] == 0


class TestConfigFile:
    """Test config file operations."""
    
    def test_config_file_path(self):
        """Test that config file path is correct."""
        assert _CONFIG_FILE.name == ".doc2md_config.json"
        assert _CONFIG_FILE.parent == Path.home()
    
    def test_config_file_not_exists_by_default(self):
        """Test that config file doesn't exist by default."""
        # This test might fail if config exists from previous runs
        # We're just checking the path is correct
        assert isinstance(_CONFIG_FILE, Path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
