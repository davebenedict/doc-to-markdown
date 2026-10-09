"""
web_app.py - Simple Flask web interface for cross-platform document conversion
"""

from flask import Flask, render_template, request, send_file, jsonify
from pathlib import Path
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

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
        image_dir = temp_dir / conv._image_asset_dir_name(output_path)
        if image_dir.is_dir():
            download_path = temp_dir / f"{tmp_path.stem}.zip"
            with ZipFile(download_path, "w", ZIP_DEFLATED) as archive:
                archive.write(output_path, output_path.name)
                for image_path in image_dir.rglob("*"):
                    if image_path.is_file():
                        archive.write(image_path, image_path.relative_to(temp_dir).as_posix())
            download_name = download_path.name
            mimetype = "application/zip"
        else:
            download_path = output_path
            download_name = tmp_path.stem + '.md'
            mimetype = 'text/markdown'

        response = send_file(
            download_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
        response.call_on_close(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return response
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Conversion error: {error_trace}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({'error': conv.friendly_error_message(e)}), 500

@app.route('/supported-formats')
def supported_formats():
    return jsonify({
        'formats': sorted(conv.SUPPORTED_EXTENSIONS),
        'missing_deps': conv.MISSING_DEPS
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
