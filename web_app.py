"""
web_app.py - Simple Flask web interface for cross-platform document conversion
"""

from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
import tempfile
import converter as conv

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Create temp directory and save file
    temp_dir = Path(tempfile.mkdtemp())
    tmp_path = temp_dir / file.filename
    file.save(str(tmp_path))

    output_path = None
    try:
        # Convert the file
        output_path = conv.convert(tmp_path)

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

@app.route('/supported-formats')
def supported_formats():
    return jsonify({
        'formats': sorted(conv.SUPPORTED_EXTENSIONS),
        'missing_deps': conv.MISSING_DEPS
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
