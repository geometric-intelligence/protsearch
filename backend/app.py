# app.py
import os
import logging

# Setup logging before imports
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)

try:
    log.info("Starting app import...")
    from api.src.index import app
    log.info("App imported successfully")
except Exception as e:
    log.error(f"Failed to import app: {e}", exc_info=True)
    raise

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    log.info(f"Starting Flask development server on port {port}")
    app.run(host='0.0.0.0', port=port)