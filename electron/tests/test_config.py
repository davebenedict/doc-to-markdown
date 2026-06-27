"""
Unit tests for configuration management
"""
import pytest
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'python'))

from web_app import _load_config, _save_config, _CONFIG_FILE


class TestConfigManagement:
    """Test configuration file operations."""
    
    @pytest.fixture
    def temp_config_file(self, tmp_path):
        """Create a temporary config file for testing."""
        config_file = tmp_path / ".doc2md_config.json"
        yield config_file
        # Cleanup
        if config_file.exists():
            config_file.unlink()
    
    def test_load_config_file_not_exists(self, tmp_path):
        """Test loading config when file doesn't exist."""
        # Temporarily change config file path
        import web_app
        original_config = web_app._CONFIG_FILE
        web_app._CONFIG_FILE = tmp_path / "nonexistent_config.json"
        
        config = _load_config()
        assert isinstance(config, dict)
        assert len(config) == 0
        
        # Restore original
        web_app._CONFIG_FILE = original_config
    
    def test_save_and_load_config(self, temp_config_file):
        """Test saving and loading configuration."""
        import web_app
        original_config = web_app._CONFIG_FILE
        web_app._CONFIG_FILE = temp_config_file
        
        test_config = {
            'output_dir': '/tmp/test',
            'remember_output_dir': True,
            'datetime_subfolder': False
        }
        
        # Save config
        _save_config(test_config)
        
        # Load config
        loaded_config = _load_config()
        
        assert loaded_config == test_config
        
        # Cleanup
        web_app._CONFIG_FILE = original_config
    
    def test_save_config_overwrites_existing(self, temp_config_file):
        """Test that saving config overwrites existing data."""
        import web_app
        original_config = web_app._CONFIG_FILE
        web_app._CONFIG_FILE = temp_config_file
        
        # Save initial config
        initial_config = {'output_dir': '/tmp/initial'}
        _save_config(initial_config)
        
        # Save new config
        new_config = {'output_dir': '/tmp/new'}
        _save_config(new_config)
        
        # Load and verify it's the new config
        loaded_config = _load_config()
        assert loaded_config == new_config
        assert loaded_config != initial_config
        
        # Cleanup
        web_app._CONFIG_FILE = original_config
    
    def test_save_config_with_all_fields(self, temp_config_file):
        """Test saving config with all supported fields."""
        import web_app
        original_config = web_app._CONFIG_FILE
        web_app._CONFIG_FILE = temp_config_file
        
        test_config = {
            'output_dir': '/tmp/output',
            'remember_output_dir': True,
            'datetime_subfolder': True
        }
        
        _save_config(test_config)
        loaded_config = _load_config()
        
        assert loaded_config['output_dir'] == test_config['output_dir']
        assert loaded_config['remember_output_dir'] == test_config['remember_output_dir']
        assert loaded_config['datetime_subfolder'] == test_config['datetime_subfolder']
        
        # Cleanup
        web_app._CONFIG_FILE = original_config


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
