#!/usr/bin/env python3
"""
Green Agent Leaderboard Generator

Scans artifacts directory for metrics.json files and generates a comprehensive leaderboard
with Elo-like ratings, comprehensive stats, and trend analysis.
"""

import json
import math
import os
import pathlib
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Tuple
import glob


class LeaderboardGenerator:
    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = pathlib.Path(artifacts_dir)
        self.leaderboard_data = {
            "last_updated": datetime.now().isoformat(),
            "agents": {},
            "runs": [],
            "summary": {}
        }
    
    def collect_all_metrics(self) -> Dict[str, List[Dict]]:
        """Collect all metrics from artifacts directory"""
        all_metrics = defaultdict(list)
        
        # Find all metrics.json files
        metrics_files = list(self.artifacts_dir.glob("*/metrics/metrics.json"))
        
        for metrics_file in metrics_files:
            run_name = metrics_file.parent.parent.name
            try:
                with open(metrics_file, 'r') as f:
                    data = json.load(f)
                
                # Handle both single-agent and multi-agent formats
                if isinstance(data, dict) and "bb_per_100" in data:
                    # Single agent format (like demo.json)
                    agent_name = self._extract_agent_name_from_path(metrics_file)
                    data["run_name"] = run_name
                    data["metrics_file"] = str(metrics_file)
                    all_metrics[agent_name].append(data)
                else:
                    # Multi-agent format (like sixmax_llm.json)
                    for agent_name, agent_data in data.items():
                        if isinstance(agent_data, dict) and "bb_per_100" in agent_data:
                            agent_data["run_name"] = run_name
                            agent_data["metrics_file"] = str(metrics_file)
                            all_metrics[agent_name].append(agent_data)
                            
            except Exception as e:
                print(f"Error reading {metrics_file}: {e}")
                continue
        
        return all_metrics
    
    def _extract_agent_name_from_path(self, metrics_file: pathlib.Path) -> str:
        """Extract agent name from file path for single-agent runs"""
        run_name = metrics_file.parent.parent.name
        # Try to infer agent name from run name or use a default
        if "demo" in run_name.lower():
            return "Demo Agent"
        return run_name.replace("_", " ").title()
    
    def calculate_composite_score(self, agent_data: List[Dict]) -> Dict[str, Any]:
        """Calculate comprehensive agent statistics and composite score"""
        if not agent_data:
            return {}
        
        # Aggregate basic stats
        total_hands = sum(run.get("hands", 0) for run in agent_data)
        bb_scores = [run.get("bb_per_100", 0) for run in agent_data if run.get("hands", 0) > 0]
        match_points = [run.get("match_points", 0) for run in agent_data]
        
        if not bb_scores:
            return {}
        
        # Calculate weighted average bb/100 (weighted by hands played)
        weighted_bb = sum(run.get("bb_per_100", 0) * run.get("hands", 0) 
                         for run in agent_data) / max(total_hands, 1)
        
        # Calculate reliability metrics
        win_rate = sum(1 for mp in match_points if mp > 0) / len(match_points)
        consistency = 1 / (1 + statistics.stdev(bb_scores)) if len(bb_scores) > 1 else 1
        
        # Performance metrics
        avg_illegal_rate = statistics.mean([run.get("illegal_actions", {}).get("per_hand", 0) 
                                          for run in agent_data])
        avg_timeout_rate = statistics.mean([run.get("timeouts", {}).get("per_hand", 0) 
                                          for run in agent_data])
        
        # Technical quality score (lower is better for illegal/timeout rates)
        tech_quality = max(0, 1 - avg_illegal_rate - avg_timeout_rate)
        
        # Behavioral consistency
        behavior_scores = []
        for run in agent_data:
            behavior = run.get("behavior", {})
            if behavior:
                vpip = behavior.get("vpip", {}).get("rate", 0)
                pfr = behavior.get("pfr", {}).get("rate", 0)
                af = behavior.get("af", 0)
                # Reasonable poker behavior score
                behavior_score = self._evaluate_poker_behavior(vpip, pfr, af)
                behavior_scores.append(behavior_score)
        
        avg_behavior_score = statistics.mean(behavior_scores) if behavior_scores else 0.5
        
        # Composite Elo-like rating
        base_rating = 1500
        bb_factor = weighted_bb * 2  # Each bb/100 = 2 rating points
        consistency_bonus = consistency * 100
        tech_bonus = tech_quality * 50
        behavior_bonus = avg_behavior_score * 100
        volume_bonus = min(math.log(total_hands + 1) * 10, 100)  # Bonus for playing more hands
        
        composite_rating = (base_rating + bb_factor + consistency_bonus + 
                          tech_bonus + behavior_bonus + volume_bonus)
        
        return {
            "composite_rating": round(composite_rating, 1),
            "total_hands": total_hands,
            "weighted_bb_per_100": round(weighted_bb, 2),
            "win_rate": round(win_rate, 3),
            "consistency": round(consistency, 3),
            "technical_quality": round(tech_quality, 3),
            "behavior_score": round(avg_behavior_score, 3),
            "runs_count": len(agent_data),
            "avg_illegal_rate": round(avg_illegal_rate, 4),
            "avg_timeout_rate": round(avg_timeout_rate, 4),
            "recent_performance": self._get_recent_performance(agent_data),
        }
    
    def _evaluate_poker_behavior(self, vpip: float, pfr: float, af: float) -> float:
        """Evaluate how reasonable the poker behavior is (0-1 scale)"""
        score = 0.5  # baseline
        
        # VPIP should be reasonable (15-85%)
        if 0.15 <= vpip <= 0.85:
            score += 0.2
        elif vpip < 0.05 or vpip > 0.95:
            score -= 0.2
        
        # PFR should be <= VPIP and reasonable
        if 0 <= pfr <= vpip and pfr >= 0.05:
            score += 0.2
        elif pfr > vpip:
            score -= 0.3
        
        # Aggression factor should be reasonable (0.5-5.0)
        if 0.5 <= af <= 5.0:
            score += 0.1
        elif af > 10:
            score -= 0.2
        
        return max(0, min(1, score))
    
    def _get_recent_performance(self, agent_data: List[Dict]) -> Dict[str, Any]:
        """Get recent performance trend"""
        if len(agent_data) < 2:
            return {"trend": "insufficient_data"}
        
        # Sort by run name (assuming chronological)
        sorted_runs = sorted(agent_data, key=lambda x: x.get("run_name", ""))
        recent_runs = sorted_runs[-3:]  # Last 3 runs
        
        bb_scores = [run.get("bb_per_100", 0) for run in recent_runs]
        
        if len(bb_scores) >= 2:
            trend = "improving" if bb_scores[-1] > bb_scores[0] else "declining"
            if abs(bb_scores[-1] - bb_scores[0]) < 10:  # Within 10 bb/100
                trend = "stable"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "recent_bb_avg": round(statistics.mean(bb_scores), 2),
            "recent_runs": len(recent_runs)
        }
    
    def generate_leaderboard(self) -> Dict[str, Any]:
        """Generate complete leaderboard data"""
        all_metrics = self.collect_all_metrics()
        
        agent_stats = {}
        for agent_name, runs in all_metrics.items():
            stats = self.calculate_composite_score(runs)
            if stats:  # Only include agents with valid data
                agent_stats[agent_name] = stats
                agent_stats[agent_name]["name"] = agent_name
                agent_stats[agent_name]["runs_data"] = runs  # Keep original data
        
        # Sort by composite rating
        sorted_agents = sorted(agent_stats.items(), 
                             key=lambda x: x[1]["composite_rating"], 
                             reverse=True)
        
        # Add rankings
        for rank, (agent_name, data) in enumerate(sorted_agents, 1):
            agent_stats[agent_name]["rank"] = rank
        
        # Generate summary statistics
        summary = self._generate_summary(agent_stats)
        
        self.leaderboard_data.update({
            "agents": agent_stats,
            "summary": summary,
            "total_agents": len(agent_stats),
            "total_runs": len(all_metrics),
        })
        
        return self.leaderboard_data
    
    def _generate_summary(self, agent_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics"""
        if not agent_stats:
            return {}
        
        ratings = [data["composite_rating"] for data in agent_stats.values()]
        bb_scores = [data["weighted_bb_per_100"] for data in agent_stats.values()]
        total_hands = sum(data["total_hands"] for data in agent_stats.values())
        
        return {
            "avg_rating": round(statistics.mean(ratings), 1),
            "top_rating": max(ratings),
            "rating_std": round(statistics.stdev(ratings) if len(ratings) > 1 else 0, 1),
            "avg_bb_per_100": round(statistics.mean(bb_scores), 2),
            "total_hands_played": total_hands,
            "competitive_agents": len([a for a in agent_stats.values() 
                                    if a["weighted_bb_per_100"] > 0]),
        }
    
    def save_leaderboard(self, output_file: str = "leaderboard/data/leaderboard.json"):
        """Save leaderboard data to JSON file"""
        output_path = pathlib.Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.leaderboard_data, f, indent=2)
        
        print(f"Leaderboard data saved to {output_path}")
        return output_path


def main():
    """Main execution function"""
    print("🏆 Generating Green Agent Leaderboard...")
    
    generator = LeaderboardGenerator()
    leaderboard_data = generator.generate_leaderboard()
    
    # Save the leaderboard
    output_file = generator.save_leaderboard()
    
    # Print summary
    print(f"\n📊 Leaderboard Summary:")
    print(f"Total Agents: {leaderboard_data['total_agents']}")
    print(f"Total Runs: {leaderboard_data['total_runs']}")
    
    if leaderboard_data['agents']:
        # Show top 5 agents
        sorted_agents = sorted(leaderboard_data['agents'].items(), 
                             key=lambda x: x[1]['rank'])
        
        print(f"\n🥇 Top 5 Agents:")
        for agent_name, data in sorted_agents[:5]:
            print(f"{data['rank']}. {agent_name}: "
                  f"{data['composite_rating']} rating "
                  f"({data['weighted_bb_per_100']:+.1f} bb/100)")
    
    print(f"\n✅ Leaderboard generated successfully!")
    return output_file


if __name__ == "__main__":
    main()