#!/usr/bin/env python3
"""
Auto-updater for Green Agent Leaderboard

Monitors the artifacts directory for changes and automatically regenerates
the leaderboard when new metrics files are detected.
"""

import time
import os
import pathlib
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from leaderboard_generator import LeaderboardGenerator
import json


class LeaderboardUpdateHandler(FileSystemEventHandler):
    def __init__(self, artifacts_dir="artifacts", output_file="leaderboard/data/leaderboard.json"):
        self.artifacts_dir = pathlib.Path(artifacts_dir)
        self.output_file = output_file
        self.generator = LeaderboardGenerator(artifacts_dir)
        self.last_hash = None
        
        # Initial generation
        self.update_leaderboard()
    
    def on_created(self, event):
        if self.is_metrics_file(event.src_path):
            print(f"📊 New metrics file detected: {event.src_path}")
            self.schedule_update()
    
    def on_modified(self, event):
        if self.is_metrics_file(event.src_path):
            print(f"📊 Metrics file updated: {event.src_path}")
            self.schedule_update()
    
    def is_metrics_file(self, file_path):
        """Check if the file is a metrics.json file"""
        return (file_path.endswith('metrics.json') and 
                'metrics' in file_path and 
                self.artifacts_dir.name in file_path)
    
    def schedule_update(self):
        """Schedule leaderboard update with debouncing"""
        # Simple debouncing - wait 2 seconds to avoid rapid updates
        time.sleep(2)
        self.update_leaderboard()
    
    def update_leaderboard(self):
        """Generate and save updated leaderboard"""
        try:
            # Calculate current hash of all metrics files
            current_hash = self.calculate_metrics_hash()
            
            if current_hash == self.last_hash:
                print("⏭️  No changes detected, skipping update")
                return
            
            print("🔄 Updating leaderboard...")
            
            # Generate new leaderboard
            leaderboard_data = self.generator.generate_leaderboard()
            output_path = self.generator.save_leaderboard(self.output_file)
            
            self.last_hash = current_hash
            
            print(f"✅ Leaderboard updated successfully!")
            print(f"📈 Total agents: {leaderboard_data.get('total_agents', 0)}")
            
            # Show top 3 agents
            if leaderboard_data.get('agents'):
                sorted_agents = sorted(leaderboard_data['agents'].items(), 
                                     key=lambda x: x[1]['rank'])[:3]
                print("🏆 Top 3:")
                for agent_name, data in sorted_agents:
                    print(f"   {data['rank']}. {agent_name}: {data['composite_rating']} rating")
            
        except Exception as e:
            print(f"❌ Error updating leaderboard: {e}")
    
    def calculate_metrics_hash(self):
        """Calculate hash of all metrics.json files for change detection"""
        hasher = hashlib.md5()
        
        metrics_files = list(self.artifacts_dir.glob("*/metrics/metrics.json"))
        metrics_files.sort()  # Ensure consistent ordering
        
        for metrics_file in metrics_files:
            if metrics_file.exists():
                with open(metrics_file, 'rb') as f:
                    hasher.update(f.read())
        
        return hasher.hexdigest()


def start_file_monitor(artifacts_dir="artifacts", output_file="leaderboard/data/leaderboard.json"):
    """Start monitoring artifacts directory for changes"""
    
    # Ensure artifacts directory exists
    artifacts_path = pathlib.Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"❌ Artifacts directory not found: {artifacts_path}")
        return
    
    # Create event handler
    event_handler = LeaderboardUpdateHandler(artifacts_dir, output_file)
    
    # Set up file system observer
    observer = Observer()
    observer.schedule(event_handler, str(artifacts_path), recursive=True)
    
    print(f"👀 Monitoring {artifacts_path} for changes...")
    print("🔄 Auto-updating leaderboard when metrics files change")
    print("💡 Press Ctrl+C to stop monitoring")
    
    try:
        observer.start()
        
        # Keep the script running and periodically check for updates
        while True:
            time.sleep(30)  # Check every 30 seconds
            event_handler.update_leaderboard()  # Periodic update in case we missed something
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping file monitor...")
        observer.stop()
    
    observer.join()
    print("✅ File monitor stopped")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Auto-update Green Agent Leaderboard')
    parser.add_argument('--artifacts-dir', default='artifacts', 
                       help='Path to artifacts directory (default: artifacts)')
    parser.add_argument('--output', default='leaderboard/data/leaderboard.json',
                       help='Output file for leaderboard data')
    parser.add_argument('--single-run', action='store_true',
                       help='Run once and exit (no monitoring)')
    
    args = parser.parse_args()
    
    if args.single_run:
        # Just update once and exit
        print("🔄 Generating leaderboard (single run)...")
        generator = LeaderboardGenerator(args.artifacts_dir)
        leaderboard_data = generator.generate_leaderboard()
        generator.save_leaderboard(args.output)
        print("✅ Leaderboard generated successfully!")
    else:
        # Start continuous monitoring
        start_file_monitor(args.artifacts_dir, args.output)


if __name__ == "__main__":
    main()