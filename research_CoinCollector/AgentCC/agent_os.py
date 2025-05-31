from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import json, os
import logging
import datetime
import re
import csv
from pathlib import Path

import textworld.gym
import gym
from balrog.environments.textworld import global_textworld_context
from balrog.environments.wrappers import GymV21CompatibilityV0

class AgentOS:
    """
    Virtual operating system that provides resources and state for the agent.
    
    This class encapsulates all the resources and state that the agent needs to operate:
    - Environment interaction
    - Memory management
    - State tracking (steps, episode status)
    
    The agent interacts with the world through this interface, which provides
    a clean abstraction layer between the agent's commands and the actual
    implementation details.
    """
    
    def __init__(self, zfile: str = "tw_games/coin_collector/level_220_seed_1171.ulx", max_steps: int = 80, csv_file: Path | None = None):
        """
        Initialize the AgentOS with a game environment.
        
        Args:
            zfile: Path to the game file
            max_steps: Maximum number of steps per episode
            csv_file: Optional path to CSV file for logging
        """
        # Load the game environment
        self.env, self.current_obs = load_game(zfile, max_steps=max_steps)
        self.current_room = parse_current_room(self.current_obs)

        self.memory: Dict[str, str] = {}  # External memory store
        self.step_count: int = 0          # Track number of steps taken
        self.done: bool = False           # Episode completion status
        self.csv_file = csv_file
        
        # Initialize CSV file if specified
        if self.csv_file:
            self.csv_file.parent.mkdir(exist_ok=True)
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Step', 'Room', 'Action', 'Result', 'Reasoning'])
    
    def log_to_csv(self, action: str, result: str, reasoning: str, room: str = None) -> None:
        """
        Helper function to log an action and its result to CSV.
        
        Args:
            action: The action taken
            result: The result/observation from the action
            reasoning: The reasoning behind the action
            room: The room (defaults to current_room if not specified)
        """
        if not self.csv_file:
            return
            
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                self.step_count,
                self.current_room if room is None else room,
                action,
                result,
                reasoning
            ])

    def read_memory(self, key: str) -> str:
        """Read a value from the agent's external memory store."""
        return self.memory.get(key, "")
    
    def write_memory(self, key: str, value: str) -> None:
        """Write a value to the agent's external memory store."""
        self.memory[key] = value
    
    def execute_game_action(self, action: str) -> str:
        """
        Execute a game action and return the observation.
        Also updates step count and episode status.
        """
        self.step_count += 1
        self.current_obs, reward, self.done, info = self.env.step(action)
        if new_room := parse_current_room(self.current_obs):
            self.current_room = new_room
        return self.current_obs

def load_game(
    ulx_file: str,
    *,
    max_steps: int = 80,
    env_name: str | None = None,
) -> Tuple[textworld.gym.Env, str]:
    """
    Initialize the TextWorld game environment.
    
    This function:
    1. Registers the game with TextWorld
    2. Creates the environment
    3. Returns the environment and initial observation
    """
    ulx_path = Path(ulx_file).expanduser().resolve()
    if not ulx_path.is_file():
        raise FileNotFoundError(f"{ulx_path} not found")

    env_id = textworld.gym.register_game(
        str(ulx_path),
        max_episode_steps=max_steps,
        name=env_name or f"ulx-{ulx_path.stem}",
    )

    env = textworld.gym.make(env_id)
    first_obs = env.reset()
    
    if isinstance(first_obs, tuple):
        first_obs_text = first_obs[0]
    else:
        first_obs_text = first_obs
    
    return env, first_obs_text

def parse_current_room(observation: str) -> str | None:
    """
    Parse the current room name from a game observation.
    The room name is formatted as '-= Room Name =-'.
    """
    pattern = re.compile(r'-=\s*(.*?)\s*=-')
    match = pattern.search(observation)
    return match.group(1) if match else None 