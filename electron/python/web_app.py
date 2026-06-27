"""
web_app.py - Simple Flask web interface for cross-platform document conversion
"""

import logging
from pathlib import Path
import tempfile
import json
import os

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)

from flask import Flask, render_template, request, send_file, jsonify
import converter as conv

# Set up template directory for Electron project
template_dir = (Path(__file__).parent.parent.parent / 'electron' / 'ui' / 'templates').resolve()
app = Flask(__name__, template_folder=str(template_dir))
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Config file for remembering settings
_CONFIG_FILE = Path.home() / ".doc2md_config.json"

# In-memory storage for converted files (for session)
_converted_files = []

def _load_config():
    """Load saved settings from config file."""
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def _save_config(config):
    """Save settings to config file."""
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except IOError:
        pass

@app.route('/')
def index():
    response = render_template('index.html')
    return response

@app.route('/config', methods=['GET', 'POST'])
def config():
    """Get or update configuration."""
    if request.method == 'GET':
        return jsonify(_load_config())
    else:
        config = request.json
        _save_config(config)
        return jsonify({'success': True})

@app.route('/converted-files', methods=['GET', 'POST'])
def converted_files():
    """Get or clear converted files list."""
    global _converted_files
    if request.method == 'GET':
        return jsonify(_converted_files)
    elif request.method == 'DELETE':
        _converted_files = []
        return jsonify({'success': True})

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Get token mode from request
    token_mode = request.form.get('token_mode', 'filesize')

    # Create temp directory and save file
    temp_dir = Path(tempfile.mkdtemp())
    tmp_path = temp_dir / file.filename
    file.save(str(tmp_path))

    output_path = None
    try:
        # Convert the file with return_text=True to get source text
        output_path, src_text = conv.convert(tmp_path, return_text=True)

        # Calculate token stats
        stats = conv.token_stats(src_text, output_path, src=tmp_path)

        # Use appropriate token count based on mode
        if token_mode == 'tiktoken' and stats.get('tiktoken_available'):
            tokens = stats.get('tiktoken_out', 0)
            savings = stats.get('tiktoken_pct', 0)
        else:
            tokens = stats.get('fallback_out', 0)
            savings = stats.get('fallback_pct', 0)

        # Calculate file sizes for display
        original_size = tmp_path.stat().st_size if tmp_path.exists() else 0
        converted_size = output_path.stat().st_size if output_path.exists() else 0

        # Add to converted files list
        file_info = {
            'name': output_path.name,
            'path': str(output_path),
            'tokens': tokens,
            'original_size': original_size,
            'converted_size': converted_size,
            'savings': savings,
            'tokenizer': 'tiktoken' if (token_mode == 'tiktoken' and stats.get('tiktoken_available')) else 'file size'
        }
        global _converted_files
        _converted_files.append(file_info)

        # Return as downloadable file
        response = send_file(
            output_path,
            as_attachment=True,
            download_name=tmp_path.stem + '.md',
            mimetype='text/markdown'
        )

        # Clean up after response is sent
        @response.call_on_close
        def cleanup():
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
                if output_path and output_path.exists():
                    output_path.unlink()
                if temp_dir.exists():
                    temp_dir.rmdir()
            except:
                pass

        return response
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Conversion error: {error_trace}")

        # Clean up on error
        try:
            if tmp_path.exists():
                tmp_path.unlink()
            if output_path and output_path.exists():
                output_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()
        except:
            pass

        return jsonify({'error': str(e), 'details': error_trace}), 500

@app.route('/convert-gdrive', methods=['POST'])
def convert_gdrive():
    """Convert Google Drive URL."""
    url = request.json.get('url')
    token_mode = request.json.get('token_mode', 'filesize')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        import google_drive as gd
        # The download function takes URL and dest_dir, doc_type is determined internally
        temp_dir = Path(tempfile.mkdtemp())
        downloaded = gd.download(url, temp_dir)
        
        # Convert with return_text=True to get source text
        output_path, src_text = conv.convert(downloaded, return_text=True)
        
        # Calculate token stats
        stats = conv.token_stats(src_text, output_path, src=downloaded)

        # Use appropriate token count based on mode
        if token_mode == 'tiktoken' and stats.get('tiktoken_available'):
            tokens = stats.get('tiktoken_out', 0)
            savings = stats.get('tiktoken_pct', 0)
        else:
            tokens = stats.get('fallback_out', 0)
            savings = stats.get('fallback_pct', 0)

        # Calculate file sizes for display
        original_size = downloaded.stat().st_size if downloaded.exists() else 0
        converted_size = output_path.stat().st_size if output_path.exists() else 0

        # Add to converted files list
        file_info = {
            'name': output_path.name,
            'path': str(output_path),
            'tokens': tokens,
            'original_size': original_size,
            'converted_size': converted_size,
            'savings': savings,
            'tokenizer': 'tiktoken' if (token_mode == 'tiktoken' and stats.get('tiktoken_available')) else 'file size'
        }
        global _converted_files
        _converted_files.append(file_info)

        # Return as downloadable file
        response = send_file(
            output_path,
            as_attachment=True,
            download_name=downloaded.stem + '.md',
            mimetype='text/markdown'
        )

        # Clean up after response is sent
        @response.call_on_close
        def cleanup():
            try:
                if downloaded.exists():
                    downloaded.unlink()
                if output_path and output_path.exists():
                    output_path.unlink()
                if temp_dir.exists():
                    temp_dir.rmdir()
            except:
                pass

        return response
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"GDrive conversion error: {error_trace}")
        return jsonify({'error': str(e), 'details': error_trace}), 500

@app.route('/supported-formats')
def supported_formats():
    return jsonify({
        'formats': sorted(conv.SUPPORTED_EXTENSIONS),
        'missing_deps': conv.MISSING_DEPS
    })

@app.route('/tiktoken-available', methods=['GET'])
def tiktoken_available():
    """Check if tiktoken is available."""
    return jsonify({'available': conv.TIKTOKEN_AVAILABLE})

@app.route('/token-count', methods=['POST'])
def token_count():
    """Count tokens for markdown content."""
    content = request.json.get('content')
    use_tiktoken = request.json.get('use_tiktoken', False)
    
    if not content:
        return jsonify({'error': 'No content provided'}), 400
    
    try:
        # Check if tiktoken is available
        if use_tiktoken and not conv.TIKTOKEN_AVAILABLE:
            return jsonify({'error': 'tiktoken not available'}), 400
        
        if use_tiktoken:
            tokens = conv._count_tokens_tiktoken(content)
        else:
            tokens = conv._count_tokens_approx(content)
        return jsonify({'tokens': tokens})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
