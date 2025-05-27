#%%
import base64
import datetime
import logging
import time
import json
import csv
import os
from collections import namedtuple
from io import BytesIO

import google.generativeai as genai
from anthropic import Anthropic
from google.generativeai import caching
from openai import OpenAI
from balrog.client import OpenAIWrapper, LLMResponse
from balrog.utils import setup_environment

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set up environment with API keys from SECRETS file
setup_environment()

# %%
# Define the test_api_call function
def test_api_call(log_data):
    """Test function to manually call the API using log parameters.
    
    Args:
        log_data (dict): Dictionary containing the API call parameters from logs.
            Expected format:
            {
                "messages": list of message dicts,
                "model": str,
                "temperature": float
            }
    
    Returns:
        LLMResponse: The response from the API.
    """
    # Create a mock client config
    class MockClientConfig:
        def __init__(self, model_id, temperature):
            self.client_name = "openai"  # Default to OpenAI
            self.model_id = model_id
            self.base_url = "https://api.deepseek.com"
            self.timeout = 30
            self.generate_kwargs = {"temperature": temperature}
            self.max_retries = 3
            self.delay = 1
            self.alternate_roles = False

    # Create client config from log data
    client_config = MockClientConfig(
        model_id=log_data["model"],
        temperature=log_data.get("temperature", 1.0)
    )
    
    # Create the appropriate client
    client = OpenAIWrapper(client_config)
    
    # Convert messages to the format expected by the client
    class Message:
        def __init__(self, role, content, attachment=None):
            self.role = role
            self.content = content
            self.attachment = attachment
    
    messages = [
        Message(msg["role"], msg["content"])
        for msg in log_data["messages"]
    ]
    
    # Make the API call
    try:
        response = client.generate(messages)
        print(f"API Call Successful!")
        print(f"Model: {response.model_id}")
        print(f"Completion: {response.completion}")
        print(f"Stop Reason: {response.stop_reason}")
        print(f"Input Tokens: {response.input_tokens}")
        print(f"Output Tokens: {response.output_tokens}")
        return response
    except Exception as e:
        print(f"API Call Failed: {str(e)}")
        raise



#%%

log_data_test1 = {
    "messages": [
        {
            "role": "user",
            "content": "You are an agent playing TextWorld, a text-based adventure game where you are in a randomly generated\n    maze and must find the coin. You need to explore different rooms to find the target object.\n    Here are the available commands: goal: print the goal of this game go <dir>: move the player north, east,\n    south, or west. You can only go in the direction indicated with something like an exit or a door. take coin:\n    2in the game by 'take coin' if you see the coin in the room\n    The only action you can do is go <dir> to explore the maze and 'take coin' when you see the coin in the\n    room.\n    You have 80 steps to complete the task. Restarting is forbidden.Observation:\n-= Bathroom =-\nYou've entered a bathroom. I guess you better just go and list everything you see here.\n\n\n\nYou need an unguarded exit? You should try going east. There is an exit to the north. Don't worry, it is unguarded. There is an exit to the west. Don't worry, it is unguarded."
        },
        {
            "role": "assistant",
            "content": "Previous plan:\n```\n<scratch-pad>\nMAP:\n- Bathroom: exits N? E? W?, visited=True\nPATH: [Bathroom]\nFirst unexplored exit in Bathroom: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
        },
        {
            "role": "user",
            "content": "Observation:\n-= Salon =-\nYou've seen better salons, but at least this one seems pretty typical. You begin to take stock of what's in the room.\n\n\n\nThere is an unblocked exit to the east. There is an exit to the north. Don't worry, it is unblocked. There is an unguarded exit to the south. You don't like doors? Why not try going west, that entranceway is unguarded."
        }
    ],
    "model": "deepseek-reasoner",
    "temperature": 1
}


#%%
cot_instructions_o3 = """



You are “Coin-Seeker-R1”, an efficient text-only agent in the TextWorld Coin-Collector game. 
Coin-Collector is a text-based adventure game where you are in a randomly generated maze and must find the coin. 
The user will tell you which room you are in and what do you observe, and you need to explore different rooms to find the target object.

Your goal: find the coin within 80 moves.
Available commands: `go north`, `go east`, `go south`, `go west`, `take coin`.
You can only `take coin` if you see the coin in the room.

To help you win the game, this the strategy that you must follow:

──────────────── Strategy ────────────────
1. **Build a mental map.**  
   • Every time you get an observation, extract:
     – `room`  : the room’s name (first line of the description)  
     – `exits` : the list after “Exits:” (N/E/S/W)  
     – `coin?` : whether the word “coin” appears (case-insensitive)  
   • Keep an internal table like  
     `MAP = {room_name: {exits:{N:?,E:?,S:?,W:?}, visited:True}}`
     N, E, S, W represent north, east, south, west, and A “?” means you haven’t tried that exit yet.
     You should avoid log a direction doesn't exist in the observation.
   • Maintain a `PATH` stack of the rooms you travelled through.

2. **Depth-first search with backtracking.**  
   Step rule:  
   a. If `coin?` is True → `ACTION = "take coin"` and stop.  
   b. Else, look at `exits` of the current room:  
      - Choose the first unexplored exit in the fixed order N, E, S, W.  
      - Push current room on `PATH`, mark that direction as “tried”,  
        set `ACTION = "go <dir>"`.  
   c. If no unexplored exits remain → pop the last room from `PATH`  
      and set `ACTION` to the direction that returns there  
      (reverse of how you came).  
   d. Repeat until coin taken or 80 steps exhausted.

3. **Update map after every move.**  
   When you arrive in a new room, fill in the reciprocal link between
   the previous room and the new one so corridors are two-way. 
   Example: If your last location is Room A and last action is `go south`,
     and now you observe that your in in Room B, then obviously you should have
      `{Room B: {exits:{N:Room A, ...}, visited:True}}`
      because Room A must be on the north side of Room B.
   You may look at your last scratch-pad and update information based on that.
   You must always keep the complete MAP. Don't truncate or discard any information that you already obtained in previous steps.

4. **Output format.**  
   Think silently, but reveal only one lowercase action to the game:
   ```
   <scratch-pad>
   …your MAP, PATH, deliberation…
   </scratch-pad>
   <|ACTION|>go north<|END|>        ← or south/east/west/take coin
   ```

5. **Be concise.**  
   Keep the scratch-pad short (≤ 60 lines) so you don’t hit token
   limits. One map line per room is enough.

Remember: no restarts, no invalid verbs, only  
`go north | go east | go south | go west | take coin`.

Good luck, Coin-Seeker-R1!
        """.strip()



# %%
# Example log data
log_data = {
  "messages": [
    {
      "role": "system",
      "content": cot_instructions_o3
    },
    {
      "role": "user",
      "content": "Observation:\n-= Bathroom =-\nYou've entered a bathroom. I guess you better just go and list everything you see here.\n\n\n\nYou need an unguarded exit? You should try going east. There is an exit to the north. Don't worry, it is unguarded. There is an exit to the west. Don't worry, it is unguarded."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n```\n<scratch-pad>\nMAP:\n- Bathroom: exits N? E? W?, visited=True\nPATH: [Bathroom]\nFirst unexplored exit in Bathroom: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Salon =-\nYou've seen better salons, but at least this one seems pretty typical. You begin to take stock of what's in the room.\n\n\n\nThere is an unblocked exit to the east. There is an exit to the north. Don't worry, it is unblocked. There is an unguarded exit to the south. You don't like doors? Why not try going west, that entranceway is unguarded."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=?, E=?, S=Bathroom, W=?, visited=True\nPATH: [Bathroom, Salon]\nFirst unexplored exit in Salon: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Workshop =-\nYou are in a workshop. A standard kind of place. You decide to just list off a complete list of everything you see in the room, because hey, why not?\n\n\n\nThere is an exit to the east. Don't worry, it is unblocked. You need an unguarded exit? You should try going north. There is an unblocked exit to the south. You need an unblocked exit? You should try going west."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=?, E=?, S=Salon, W=?, visited=True\nPATH: [Bathroom, Salon, Workshop]\nFirst unexplored exit in Workshop: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Silent Office =-\nI am honoured to announce that you are now in the silent office.\n\n\n\nThere is an unblocked exit to the south."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=?, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\nPATH: [Bathroom, Salon, Workshop, Silent Office]\nNo coin here. Backtracking to Workshop via south exit. Next explore Workshop's east exit.\n</scratch-pad>\n<|ACTION|>go south<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Workshop =-\nYou are in a workshop. A standard kind of place. You decide to just list off a complete list of everything you see in the room, because hey, why not?\n\n\n\nThere is an exit to the east. Don't worry, it is unblocked. You need an unguarded exit? You should try going north. There is an unblocked exit to the south. You need an unblocked exit? You should try going west."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=?, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\nPATH: [Bathroom, Salon, Workshop]\nFirst unexplored exit in Workshop: E\n</scratch-pad>\n<|ACTION|>go east<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Playroom =-\nYou arrive in a playroom. You try to gain information on your surroundings by using a technique you call \"looking.\"\n\n\n\nThere is an unguarded exit to the east. There is an exit to the north. Don't worry, it is unguarded. You need an unguarded exit? You should try going south. You don't like doors? Why not try going west, that entranceway is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=?, E=?, S=?, W=Workshop, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom]\nFirst unexplored exit in Playroom: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Fun Salon =-\nYou are in a salon. A fun one.\n\n\n\nThere is an unguarded exit to the south."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=?, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Fun Salon]\nNo coin here. No unexplored exits. Backtracking to Playroom via south.\n</scratch-pad>\n<|ACTION|>go south<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Playroom =-\nYou arrive in a playroom. You try to gain information on your surroundings by using a technique you call \"looking.\"\n\n\n\nThere is an unguarded exit to the east. There is an exit to the north. Don't worry, it is unguarded. You need an unguarded exit? You should try going south. You don't like doors? Why not try going west, that entranceway is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=?, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom]\nFirst unexplored exit in Playroom: E\n</scratch-pad>\n<|ACTION|>go east<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Austere Workshop =-\nYou've fallen into an austere room. Your mind races to think of what kind of room would be austere. And then it hits you. Of course. You're in the austere workshop.\n\n\n\nYou need an unguarded exit? You should try going east. There is an exit to the north. Don't worry, it is unblocked. There is an exit to the south. Don't worry, it is unblocked. There is an unguarded exit to the west."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=?, E=?, S=?, W=Playroom, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop]\nFirst unexplored exit in Austere Workshop: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Cramped Bathroom =-\nYou arrive in a bathroom. A cramped kind of place.\n\n\n\nThere is an exit to the south. Don't worry, it is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=?, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop]\nNo exits left in Cramped Bathroom. Backtracking to Austere Workshop via south.\n</scratch-pad>\n<|ACTION|>go south<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Austere Workshop =-\nYou've fallen into an austere room. Your mind races to think of what kind of room would be austere. And then it hits you. Of course. You're in the austere workshop.\n\n\n\nYou need an unguarded exit? You should try going east. There is an exit to the north. Don't worry, it is unblocked. There is an exit to the south. Don't worry, it is unblocked. There is an unguarded exit to the west."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=?, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop]\nFirst unexplored exit in Austere Workshop: E\n</scratch-pad>\n<|ACTION|>go east<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Silent Studio =-\nYou find yourself in a studio. A silent one.\n\n\n\nYou need an unguarded exit? You should try going east. There is an unblocked exit to the north. There is an exit to the south. Don't worry, it is unguarded. There is an exit to the west. Don't worry, it is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=Silent Studio, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\n- Silent Studio: exits N=?, E=?, S=?, W=Austere Workshop, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop, Silent Studio]\nFirst unexplored exit in Silent Studio: N\n</scratch-pad>\n<|ACTION|>go north<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Pantry =-\nYou are in a pantry. An usual one. You try to gain information on your surroundings by using a technique you call \"looking.\"\n\n\n\nYou don't like doors? Why not try going south, that entranceway is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=Silent Studio, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\n- Silent Studio: exits N=Pantry, E=?, S=?, W=Austere Workshop, visited=True\n- Pantry: exits S=Silent Studio, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop, Silent Studio, Pantry]\nNo exits left in Pantry. Backtracking to Silent Studio via south.\n</scratch-pad>\n<|ACTION|>go south<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Silent Studio =-\nYou find yourself in a studio. A silent one.\n\n\n\nYou need an unguarded exit? You should try going east. There is an unblocked exit to the north. There is an exit to the south. Don't worry, it is unguarded. There is an exit to the west. Don't worry, it is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=Silent Studio, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\n- Silent Studio: exits N=Pantry, E=?, S=?, W=Austere Workshop, visited=True\n- Pantry: exits S=Silent Studio, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop, Silent Studio]\nFirst unexplored exit in Silent Studio: E\n</scratch-pad>\n<|ACTION|>go east<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Cellar =-\nYou find yourself in a cellar. An ordinary one.\n\n\n\nYou need an unguarded exit? You should try going west."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=Silent Studio, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\n- Silent Studio: exits N=Pantry, E=Cellar, S=?, W=Austere Workshop, visited=True\n- Pantry: exits S=Silent Studio, visited=True\n- Cellar: exits W=Silent Studio, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop, Silent Studio, Cellar]\nNo exits left in Cellar. Backtracking to Silent Studio via west.\n</scratch-pad>\n<|ACTION|>go west<|END|>"
    },
    {
      "role": "user",
      "content": "Observation:\n-= Silent Studio =-\nYou find yourself in a studio. A silent one.\n\n\n\nYou need an unguarded exit? You should try going east. There is an unblocked exit to the north. There is an exit to the south. Don't worry, it is unguarded. There is an exit to the west. Don't worry, it is unblocked."
    },
    {
      "role": "assistant",
      "content": "My Reasoning and Action:\n<scratch-pad>\nMAP:\n- Bathroom: exits N=Salon, E=?, W=?, visited=True\n- Salon: exits N=Workshop, E=?, S=Bathroom, W=?, visited=True\n- Workshop: exits N=Silent Office, E=Playroom, S=Salon, W=?, visited=True\n- Silent Office: exits S=Workshop, visited=True\n- Playroom: exits N=Fun Salon, E=Austere Workshop, S=?, W=Workshop, visited=True\n- Fun Salon: exits S=Playroom, visited=True\n- Austere Workshop: exits N=Cramped Bathroom, E=Silent Studio, S=?, W=Playroom, visited=True\n- Cramped Bathroom: exits S=Austere Workshop, visited=True\n- Silent Studio: exits N=Pantry, E=Cellar, S=?, W=Austere Workshop, visited=True\n- Pantry: exits S=Silent Studio, visited=True\n- Cellar: exits W=Silent Studio, visited=True\nPATH: [Bathroom, Salon, Workshop, Playroom, Austere Workshop, Silent Studio]\nFirst unexplored exit in Silent Studio: S\n</scratch-pad>\n<|ACTION|>go south<|END|>"
    },
    {
      "role": "user",
      "content": "Current Observation:\n-= Fun Recreation Zone =-\nYou arrive in a recreation zone. A fun kind of place.\n\n\n\nYou need an unblocked exit? You should try going east. There is an unblocked exit to the north. There is an unguarded exit to the south. You don't like doors? Why not try going west, that entranceway is unguarded.\n" 
      + cot_instructions_o3
    }
  ],
  "model": "deepseek-reasoner",
  "temperature": 1
}

# Make the API call
response = test_api_call(log_data)
# %%
