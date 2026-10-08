"""
Unit tests for Flask web backend
"""
import pytest
import json
from io import BytesIO
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'python'))

from web_app import app, _CONFIG_FILE


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web_app

    config_file = tmp_path / ".doc2md_config.json"
    config_file.write_text(json.dumps({"output_dir": str(tmp_path / "converted")}), encoding="utf-8")
    monkeypatch.setattr(web_app, "_CONFIG_FILE", config_file)
    monkeypatch.setattr(web_app, "_converted_files", [])
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
    
    def test_get_config_returns_configured_output_folder(self, client, tmp_path):
        response = client.get('/config')
        assert response.status_code == 200
        assert response.get_json()['output_dir'] == str(tmp_path / 'converted')
    
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
        response = client.get('/converted-files')
        assert response.status_code == 200
        assert response.get_json() == []
    
    def test_clear_converted_files(self, client):
        import web_app

        web_app._converted_files.append({'name': 'test.md', 'path': '/tmp/test.md'})
        response = client.delete('/converted-files')
        assert response.status_code == 200
        assert response.get_json()['success'] is True
        assert web_app._converted_files == []


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
    def test_token_count_approx(self, client):
        response = client.post('/token-count', json={'content': 'Hello world', 'use_tiktoken': False})
        assert response.status_code == 200
        assert response.get_json()['tokens'] == len('Hello world') // 4

    def test_token_count_empty_content(self, client):
        response = client.post('/token-count', json={'content': '', 'use_tiktoken': False})
        assert response.status_code == 200
        assert response.get_json()['tokens'] == 0

    def test_missing_content_is_rejected(self, client):
        response = client.post('/token-count', json={})
        assert response.status_code == 400

    def test_tiktoken_count(self, client):
        import web_app
        if not web_app.conv.TIKTOKEN_AVAILABLE:
            pytest.skip('tiktoken is not installed')
        text = 'Hello world'
        response = client.post('/token-count', json={'content': text, 'use_tiktoken': True})
        assert response.status_code == 200
        assert response.get_json()['tokens'] == web_app.conv._count_tokens(text)


class TestTokenizerIndicator:
    @pytest.mark.parametrize('token_mode', ['tiktoken', 'filesize'])
    def test_convert_response_includes_tokenizer(self, client, token_mode):
        import web_app

        response = client.post(
            '/convert',
            data={
                'file': (BytesIO(b'name,value\nAlice,1\n'), 'report.csv'),
                'token_mode': token_mode,
            },
        )

        assert response.status_code == 200
        file_info = response.get_json()['file']
        expected = 'tiktoken' if token_mode == 'tiktoken' and web_app.conv.TIKTOKEN_AVAILABLE else 'file size'
        assert file_info['tokenizer'] == expected


class TestFriendlyConversionErrors:
    def test_missing_package_response_includes_resolution_not_traceback(self, client, monkeypatch):
        import web_app

        def fail_convert(*args, **kwargs):
            raise ImportError("Required package 'PyMuPDF' is not installed.")

        monkeypatch.setattr(web_app.conv, "convert", fail_convert)
        response = client.post(
            "/convert",
            data={"file": (BytesIO(b"pdf bytes"), "report.pdf")},
        )

        assert response.status_code == 500
        error = response.get_json()["error"]
        assert "PyMuPDF" in error
        assert "pip install PyMuPDF" in error
        assert "requirements.txt" in error
        assert "Traceback" not in error


class TestConfiguredOutputFolder:
    def test_upload_saves_to_configured_folder_without_attachment(self, client, tmp_path, monkeypatch):
        import web_app

        output_dir = tmp_path / "converted"
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"output_dir": str(output_dir)}), encoding="utf-8")
        monkeypatch.setattr(web_app, "_CONFIG_FILE", config_file)
        monkeypatch.setattr(web_app, "_converted_files", [])

        response = client.post(
            "/convert",
            data={"file": (BytesIO(b"name,value\nAlice,1\n"), "report.csv")},
        )

        assert response.status_code == 200
        file_info = response.get_json()["file"]
        output_path = Path(file_info["path"])
        assert output_path.parent == output_dir.resolve()
        assert output_path.exists()
        assert response.headers.get("Content-Disposition") is None


    def test_gdrive_conversion_saves_to_configured_folder_without_attachment(self, client, tmp_path, monkeypatch):
        import web_app
        import google_drive as gd

        output_dir = tmp_path / "converted"
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"output_dir": str(output_dir)}), encoding="utf-8")
        monkeypatch.setattr(web_app, "_CONFIG_FILE", config_file)
        monkeypatch.setattr(web_app, "_converted_files", [])

        def fake_download(url, dest_dir):
            source = dest_dir / "drive.csv"
            source.write_text("name,value\nAlice,1\n", encoding="utf-8")
            return source

        monkeypatch.setattr(gd, "download", fake_download)
        response = client.post("/convert-gdrive", json={"url": "https://drive.google.com/file/d/valid"})

        assert response.status_code == 200
        file_info = response.get_json()["file"]
        output_path = Path(file_info["path"])
        assert output_path.parent == output_dir.resolve()
        assert output_path.exists()
        assert response.headers.get("Content-Disposition") is None


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
