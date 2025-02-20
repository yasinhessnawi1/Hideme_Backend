import os
import logging
from flask import Flask
from src.api.routes import api_blueprint

# Initialize Flask App
app = Flask(__name__)

# Register API routes from `src/api/routes.py`
app.register_blueprint(api_blueprint, url_prefix='/api')

if __name__ == '__main__':
    # Run Flask App
    port = int(os.getenv("PORT", 5000))  # Default to port 5000
    logging.info(f"🚀 Server running on http://127.0.0.1:{port}/api")
    app.run(debug=True, host='0.0.0.0', port=port)
