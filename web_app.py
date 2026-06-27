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

    # Save uploaded file to temp directory
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        file.save(tmp.name)
        tmp_path = Path(tmp.name)

    output_path = None
    try:
        # Convert the file
        output_path = conv.convert(tmp_path)

        # Return as downloadable file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=tmp_path.stem + '.md',
            mimetype='text/markdown'
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Conversion error: {error_trace}")
        return jsonify({'error': str(e), 'details': error_trace}), 500
    finally:
        # Clean up temp files
        if tmp_path.exists():
            tmp_path.unlink()
        if output_path and output_path.exists():
            output_path.unlink()

@app.route('/supported-formats')
def supported_formats():
    return jsonify({
        'formats': sorted(conv.SUPPORTED_EXTENSIONS),
        'missing_deps': conv.MISSING_DEPS
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
