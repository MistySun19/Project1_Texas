#!/usr/bin/env python3
"""
Simple HTTP server for Green Agent Leaderboard

Serves the leaderboard web interface and provides API endpoints for data access.
"""

import http.server
import socketserver
import json
import os
import pathlib
import webbrowser
import threading
import time
from urllib.parse import urlparse, parse_qs


class LeaderboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="leaderboard", **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # API endpoint for leaderboard data
        if parsed_path.path == '/api/leaderboard':
            self.serve_api_data()
        # API endpoint to trigger refresh
        elif parsed_path.path == '/api/refresh':
            self.refresh_leaderboard()
        else:
            # Serve static files
            super().do_GET()
    
    def serve_api_data(self):
        """Serve leaderboard data as JSON API"""
        try:
            data_file = pathlib.Path("leaderboard/data/leaderboard.json")
            if data_file.exists():
                with open(data_file, 'r') as f:
                    data = json.load(f)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data, indent=2).encode())
            else:
                self.send_error(404, "Leaderboard data not found")
        except Exception as e:
            self.send_error(500, f"Error serving data: {e}")
    
    def refresh_leaderboard(self):
        """Trigger leaderboard refresh"""
        try:
            # Import here to avoid circular imports
            from leaderboard_generator import LeaderboardGenerator
            
            print("🔄 API refresh request received...")
            generator = LeaderboardGenerator()
            leaderboard_data = generator.generate_leaderboard()
            generator.save_leaderboard()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                "status": "success",
                "message": "Leaderboard refreshed successfully",
                "timestamp": leaderboard_data.get("last_updated"),
                "total_agents": leaderboard_data.get("total_agents", 0)
            }
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_error(500, f"Error refreshing leaderboard: {e}")
    
    def log_message(self, format, *args):
        """Override to provide better logging"""
        message = format % args
        print(f"🌐 {self.address_string()} - {message}")


def ensure_leaderboard_data():
    """Ensure leaderboard data exists before starting server"""
    data_file = pathlib.Path("leaderboard/data/leaderboard.json")
    
    if not data_file.exists():
        print("📊 Generating initial leaderboard data...")
        try:
            from leaderboard_generator import LeaderboardGenerator
            generator = LeaderboardGenerator()
            generator.generate_leaderboard()
            generator.save_leaderboard()
            print("✅ Initial leaderboard data generated")
        except Exception as e:
            print(f"❌ Failed to generate initial data: {e}")
            return False
    
    return True


def start_server(port=8000, auto_open=True):
    """Start the leaderboard server"""
    
    # Ensure we're in the right directory
    os.chdir(pathlib.Path(__file__).parent.parent)
    
    # Ensure leaderboard data exists
    if not ensure_leaderboard_data():
        return
    
    # Create server
    try:
        with socketserver.TCPServer(("", port), LeaderboardHandler) as httpd:
            server_url = f"http://localhost:{port}"
            
            print(f"🚀 Green Agent Leaderboard Server Starting...")
            print(f"📍 Server URL: {server_url}")
            print(f"📊 Leaderboard: {server_url}/")
            print(f"🔧 API Data: {server_url}/api/leaderboard")
            print(f"🔄 API Refresh: {server_url}/api/refresh")
            print(f"💡 Press Ctrl+C to stop the server")
            
            # Auto-open browser
            if auto_open:
                def open_browser():
                    time.sleep(1)  # Wait for server to start
                    try:
                        webbrowser.open(server_url)
                        print(f"🌐 Opened {server_url} in browser")
                    except Exception as e:
                        print(f"⚠️  Could not auto-open browser: {e}")
                
                threading.Thread(target=open_browser, daemon=True).start()
            
            # Start serving
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ Port {port} is already in use. Try a different port:")
            print(f"   python leaderboard/server.py --port {port + 1}")
        else:
            print(f"❌ Server error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Green Agent Leaderboard Server')
    parser.add_argument('--port', type=int, default=8000,
                       help='Port to serve on (default: 8000)')
    parser.add_argument('--no-browser', action='store_true',
                       help='Do not auto-open browser')
    
    args = parser.parse_args()
    
    start_server(port=args.port, auto_open=not args.no_browser)


if __name__ == "__main__":
    main()