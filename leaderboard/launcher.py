#!/usr/bin/env python3
"""
Green Agent Leaderboard Launcher

One-click launcher for the complete leaderboard system with monitoring and web server.
"""

import subprocess
import threading
import time
import pathlib
import signal
import sys
import os


class LeaderboardLauncher:
    def __init__(self):
        self.processes = []
        self.running = True
        
        # Ensure we're in the project root
        os.chdir(pathlib.Path(__file__).parent.parent)
    
    def start_component(self, name, command, description):
        """Start a component in a separate process"""
        print(f"🚀 Starting {name}: {description}")
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            self.processes.append((name, process))
            
            # Start thread to monitor output
            threading.Thread(
                target=self.monitor_process,
                args=(name, process),
                daemon=True
            ).start()
            
            return True
        except Exception as e:
            print(f"❌ Failed to start {name}: {e}")
            return False
    
    def monitor_process(self, name, process):
        """Monitor process output"""
        while self.running and process.poll() is None:
            try:
                line = process.stdout.readline()
                if line:
                    print(f"[{name}] {line.strip()}")
            except Exception:
                break
    
    def stop_all(self):
        """Stop all processes"""
        print("\n🛑 Stopping all components...")
        self.running = False
        
        for name, process in self.processes:
            try:
                print(f"⏹️  Stopping {name}...")
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"🔨 Force killing {name}...")
                    process.kill()
                    
            except Exception as e:
                print(f"⚠️  Error stopping {name}: {e}")
        
        print("✅ All components stopped")
    
    def launch_full_system(self, port=8000, auto_monitor=True):
        """Launch the complete leaderboard system"""
        print("🏆 Green Agent Leaderboard - Full System Launch")
        print("=" * 50)
        
        # Step 1: Generate initial leaderboard data
        print("📊 Generating initial leaderboard data...")
        result = subprocess.run([
            "python", "leaderboard/leaderboard_generator.py"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Failed to generate initial data: {result.stderr}")
            return False
        
        print("✅ Initial leaderboard data generated")
        
        # Step 2: Start auto-updater (if requested)
        if auto_monitor:
            self.start_component(
                "Monitor",
                "python leaderboard/auto_updater.py",
                "File system monitor for automatic updates"
            )
            time.sleep(2)  # Let monitor start
        
        # Step 3: Start web server
        self.start_component(
            "Server",
            f"python leaderboard/server.py --port {port}",
            f"Web server on http://localhost:{port}"
        )
        
        print("\n" + "=" * 50)
        print("🎉 Green Agent Leaderboard is now running!")
        print(f"🌐 Access the leaderboard at: http://localhost:{port}")
        
        if auto_monitor:
            print("👀 Monitoring artifacts/ directory for automatic updates")
        
        print("💡 Press Ctrl+C to stop all components")
        print("=" * 50)
        
        return True
    
    def launch_server_only(self, port=8000):
        """Launch just the web server"""
        print("🌐 Launching Green Agent Leaderboard Server Only")
        print("=" * 50)
        
        # Generate data first
        print("📊 Generating leaderboard data...")
        result = subprocess.run([
            "python", "leaderboard/leaderboard_generator.py"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Failed to generate data: {result.stderr}")
            return False
        
        # Start server
        self.start_component(
            "Server",
            f"python leaderboard/server.py --port {port}",
            f"Web server on http://localhost:{port}"
        )
        
        print(f"🌐 Leaderboard available at: http://localhost:{port}")
        print("💡 Use the refresh button in the web interface to update data")
        print("💡 Press Ctrl+C to stop the server")
        
        return True


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    if hasattr(signal_handler, 'launcher'):
        signal_handler.launcher.stop_all()
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Green Agent Leaderboard Launcher')
    parser.add_argument('--port', type=int, default=8000,
                       help='Web server port (default: 8000)')
    parser.add_argument('--server-only', action='store_true',
                       help='Launch only the web server (no auto-monitoring)')
    parser.add_argument('--no-monitor', action='store_true',
                       help='Disable automatic file monitoring')
    
    args = parser.parse_args()
    
    # Create launcher
    launcher = LeaderboardLauncher()
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal_handler.launcher = launcher
    
    try:
        if args.server_only:
            success = launcher.launch_server_only(args.port)
        else:
            success = launcher.launch_full_system(args.port, not args.no_monitor)
        
        if success:
            # Keep the main process alive
            while launcher.running:
                time.sleep(1)
        
    except KeyboardInterrupt:
        pass
    finally:
        launcher.stop_all()


if __name__ == "__main__":
    main()