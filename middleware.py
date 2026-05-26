"""
middleware.py
Provides basic rate limiting, request logging, and error handling.
"""

from flask import request, jsonify
import time
import logging

logger = logging.getLogger(__name__)

# Very basic in-memory rate limiting map
_rate_limits = {}

def apply_middleware(app):
    @app.before_request
    def rate_limit_check():
        # Exclude static assets
        if request.path.startswith("/static/"):
            return None
            
        ip = request.remote_addr
        now = time.time()
        
        if ip not in _rate_limits:
            _rate_limits[ip] = []
            
        # Clean up old requests (>60s)
        _rate_limits[ip] = [ts for ts in _rate_limits[ip] if now - ts < 60]
        
        # Max 60 requests per minute
        if len(_rate_limits[ip]) > 60:
            return jsonify({"error": "Rate limit exceeded"}), 429
            
        _rate_limits[ip].append(now)

    @app.after_request
    def log_request(response):
        if not request.path.startswith("/static/"):
            logger.info(f"{request.method} {request.path} - {response.status_code}")
        return response
        
    @app.errorhandler(500)
    def handle_500(e):
        logger.error(f"Server Error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500
