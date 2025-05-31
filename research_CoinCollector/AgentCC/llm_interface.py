from typing import List, Dict
import json
import os
from openai import OpenAI

# Define the tools available to the agent
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Read a value from the agent's memory store",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key to read from memory"
                    }
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "Write a value to the agent's memory store",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The key to write to memory"
                    },
                    "value": {
                        "type": "string",
                        "description": "The value to write to memory"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "game_action",
            "description": "Execute a game action in the TextWorld environment",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The game action to execute. "
                        "Available actions : 'go north', 'go south', 'go east', 'go west', 'take coin'"
                    }
                },
                "required": ["action"]
            }
        }
    }
]

LLM_system_prompt_V1 = (
    "You are an agent playing TextWorld Coin Collector.\n"
    "You have access to the following tools:\n"
    "1. read_memory - Read a value from memory\n"
    "2. write_memory - Write a value to memory\n"
    "3. game_action - Execute a game action\n\n"
    """
    In the first round, read the introduction, think about the strategy, and 
    come up with a playbook (an operational plan) for yourself to follow in the future.
    Save the playbook in memory with the key 'Playbook'.
    In the 'Playbook', you should indicate which memory keys you will read and write in each round,
    and what are their usages.
    """
    "In each round, review your 'Playbook' first.\n"
    "Write anything you want your future self to know in memory with the key 'Notes'.\n"
    "In each round, you must choose at least one of the tools to push the game forward."

    """
    Some information about the game:
    A. Coin Collector has simple mazes and DFS algorithm is enough to solve it.
    B. You can ONLY 'take coin' when the observation explicitly mentions the coin.
    """
)


LLM_system_prompt_V2_weaker = (
    "You are an agent playing TextWorld Coin Collector.\n"
    "You have access to the following tools:\n"
    "1. read_memory - Read a value from memory\n"
    "2. write_memory - Write a value to memory\n"
    "3. game_action - Execute a game action\n\n"
    """
    In the first round, read the introduction, think about the strategy, and 
    come up with a playbook (an operational plan) for yourself to follow in the future.
    Save the playbook in memory with the key 'Playbook'.
    In the 'Playbook', you should indicate which memory keys you will read and write in each round,
    and what are their usages.
    """
    "In each round, review your 'Playbook' first.\n"
    "Write anything you want your future self to know in memory with the key 'Notes'.\n"
    "In each round, you must choose at least one of the tools to push the game forward."

    """
    Some information about the game:
    A. Coin Collector has simple mazes.
    B. You can ONLY 'take coin' when the observation explicitly mentions the coin.
    """
)


LLM_system_prompt_DFS = (
    "You are a LLM agent playing TextWorld Coin Collector.\n"
    "You are a special agent with external memory. You have access to the following tools:\n"
    "1. read_memory - Read a value from memory\n"
    "2. write_memory - Write a value to memory\n"
    "3. game_action - Execute a game action\n\n"

    """
    Playbook for the game:
    Keep an internal table like  
    Use memory key "MAP" to keep information of all visited rooms and exits. Example:
      {room_name_1: {exits:{N:?,E:?,S:?,W:?}}, ...}
    Use memory key "PATH" to keep the stack of path you have taken. Example:
      [room_name_1, room_name_2, ...]
    Use memory key "CURRENT_ROOM" to keep the current room you are in. 

    When you arrive in a new room, update the MAP for current room and previous room, fill their exits reciprocally.
    Note: some rooms may not have exits to all directions. Mark unmentioned exits as Invalid.

    Use DFS algorithm to explore the maze:
    - Choose the first unexplored exit in the fixed order N, E, S, W
    - If the current room has no unexplored exits, pop the last room from `PATH` and go to the last room in the path
    - Take coin only if the room description explicitly mentions the coin.

    """
)

LLM_system_prompt_DFS_weaker = """
1. **Memory Keys and Usage:**
   - 'Current_Location': Track the current room (e.g., 'Bathroom').
   - 'Visited_Rooms': List of rooms already visited to avoid loops.
   - 'Coins_Collected': Track the number of coins collected.
   - 'Path': Record the path taken for backtracking if needed.

2. **Strategy:**
   - Use DFS to explore the maze.
   - Always check for coins in the current room before moving.
   - Prioritize unexplored directions (north, south, east, west) based on the current location.
   - Avoid revisiting rooms unless necessary for backtracking.

3. **Actions per Round:**
   - Read 'Current_Location' and 'Visited_Rooms'.
   - Check for coins in the observation.
   - If a coin is present, 'take coin' and update 'Coins_Collected'.
   - If no coin, choose an unexplored direction, update 'Path' and 'Visited_Rooms', and move.
   - Write updates to memory after each action.
"""

LLM_system_prompt_DFS_strong ="""

You are “Coin-Seeker-R1”, an efficient text-only agent in the TextWorld Coin-Collector game. 
Coin-Collector is a text-based adventure game where you are in a randomly generated maze and must find the coin. 
The user will tell you which room you are in and what do you observe, and you need to explore different rooms to find the target object.

Your goal: find the coin within 200 moves.
Available commands: `go north`, `go east`, `go south`, `go west`, `take coin`.
You can only `take coin` if you see the coin in the room.

To help you win the game, this the strategy that you must follow:

──────────────── Strategy ────────────────
1. **Build a mental map.**  
   • Keep an internal table like  
     `MAP = {
     room_name_1: {exits:{N:?,E:?,S:?,W:?}},\n
     room_name_2: {exits:{N:?,E:?,S:?,W:?}},\n
     ...}`
     (Write one line per room. N, E, S, W represent North, East, South, West, and "?" means unknown exit.)
     
   • Maintain a `PATH = {room_A, room_B, ...}` stack of the rooms you travelled through.

2. **Update map when you arrive in a new room.**  
   • When you arrive in a new room and get an observation, extract:
       `room`  : the room’s name (first line of the observation)  
       `exits` : the list of exits mentioned in the observation
   • Update the MAP :
       • You should first copy your last MAP, PATH from the previous step and 
         then update information based on the current observation.    
       • Update the `exits` of the current room based on the observation. 
         If an exit is not mentioned in the observation, mark it as `Invalid`.
       • fill in the reciprocal link between the previous room and the new one so corridors are two-way. 
         Example: If your last location is Room A and last action is `go south`,
                  and now you observe that your in in Room B, then obviously you should have
                  `{Room A: {exits:{S:Room B, ...}, ...},Room B: {exits:{N:Room A, ...}, ...}}`.
   • Update the PATH :
       • Push current room on `PATH`

3. **Depth-first search (DFS) with backtracking.**  
   Step rule:  
   a. If `coin` is mentioned in the observation → `action = "take coin"` and stop.  
   b. Else, check the `exits` of the current room:  
      - Choose the first unexplored exit (i.e. leads to unvisited room) in the fixed order N, E, S, W.  
        set `action = "go <direction>"`.  
   c. If no unexplored exits remain → pop the last room from `PATH`  
      then set `action` to the direction to return to the last room in `PATH`.
   d. Repeat until coin taken or 80 steps exhausted.

4. **Output format.**  
   ```
   <scratch-pad>
   your MAP, PATH, your NOTES
   </scratch-pad>
   ```
   Use tool `game_action(action)` to interact with the game, where `action` is from `go north | go east | go south | go west | take coin`.

5. **Checklist.**
   In every step, after write down MAP, PATH, double check everything.
     Here is a checklist: 
     - C1: Which room I am currently in? What are the available exits? Which room did I come from?
     - C2: Did I copy previous MAP, PATH correctly? Did I update the reciprocal link the current <--> previous room with opposite direction correctly?
     - C3: Do I have any missing information in MAP, PATH, and no abbreviation? 
     - C4: Am I following the DFS strategy? Or am I in the process of error recovery?
     Write down your answer to ALL of the above questions in the NOTES in the scratch-pad:

6. **Discipline, Responsibility and Error Recovery.** 
   • The GOLD RULE for the game : in every step, in your `scratch-pad`, you must always 
     keep a complete MAP of all visited rooms and their exits from previous observations. 
     NEVER discard or compress any information in the MAP, PATH. NEVER use any abbreviation in the MAP, PATH (such as "..."). 
     If you ever find any missing information in the MAP, PATH, your highest priority is to complete 
     the MAP based on previous steps. NEVER mindlessly explore without a MAP.
   • Error Recovery:
     Seeing anything unexpected means you might have made a mistaken and possibly ruined the DFS strategy.
     In such a case, instead of following the DFS strategy mindlessly, you should try to understand the mistake and try to recover from the mistake.
     Here are some common mistakes and how to recover:
     - If you see 'That's not a verb I recognise', it means your last action is not valid and you are still in the same room.
     - If you see 'You can't go that way', it means your last choice of direction is not valid and you are still in the same room.
     The game setup is absolutely correct. If you can't find the coin, you must have made mistakes.
     In the worse scenario, if you really can't figure out the mistake, you may discard all previous MAP, PATH and start over from the current room.


Good luck, Coin-Seeker-R1!
        """


def bootstrap_prompt(initial_obs: str) -> List[dict]:
    """
    Create the initial system prompt and first observation.
    
    The system prompt explains the agent's capabilities and available tools,
    while the first observation provides the initial game state.
    """
    return [
        {
            "role": "system",
            "content": LLM_system_prompt_DFS_strong,
        },
        {"role": "user", "content": initial_obs},
    ]


def create_client(
    api_key: str | None = None,
    *,
    base_url: str = "https://api.deepseek.com",
) -> OpenAI:
    """Create and configure the DeepSeek API client."""
    if api_key is None:
        try:
            with open("SECRETS", "r") as f:
                for line in f:
                    if line.startswith("OPENAI_API_KEY="):
                        api_key = line.strip().split("=")[1]
                        break
        except FileNotFoundError:
            print("Warning: SECRETS file not found. Using environment variable DEEPSEEK_API_KEY.")
            api_key = os.getenv("OPENAI_API_KEY")
    
    return OpenAI(api_key=api_key, base_url=base_url)


def next_model_message(
    client: OpenAI,
    messages: List[dict],
    temperature: float = 0.2,
    model: str = "deepseek-reasoner",
):
    """ Get the next message from the LLM. """
    # Create base parameters
    params = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
    }
    
    # Only add temperature if model doesn't start with o3 or o4
    if not (model.startswith("o3") or model.startswith("o4")):
        params["temperature"] = temperature
        
    resp = client.chat.completions.create(**params)
    msg = resp.choices[0].message
    
    return msg 