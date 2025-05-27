import copy
import re
import json
import os
from datetime import datetime
from pathlib import Path

from balrog.agents.base import BaseAgent
from balrog.client import LLMClientWrapper





        # Updated instructions: chain of thought + strict output format
cot_instructions_V0 = """
First, think about the best course of action. You should form a 2D map in your head with visited rooms. You could state the previous path explicitly to help form the map, especially if you are entering a previously visited room.
Then, you must choose exactly one of the listed actions and output it strictly in the following format:

<|ACTION|>YOUR_CHOSEN_ACTION<|END|>

Replace YOUR_CHOSEN_ACTION with the chosen action.
Note : The coin is not in the Vault room, which is just an ordinary room.
        """.strip()

cot_instructions_V1 = """
First, think about the best course of action. You should form a 2D map in your head with visited rooms. To help form the map, summarize previous steps explicitly, marking the explored and unexplored directions.
Then, you must choose exactly one of the listed actions and output it strictly in the following format:

<|ACTION|>YOUR_CHOSEN_ACTION<|END|>

Replace YOUR_CHOSEN_ACTION with the chosen action.
Note : The coin is not in the Vault room, which is just an ordinary room.
        """.strip()

cot_instructions_V2 = """
First, think about the best course of action. You should form a 2D map in your head with visited rooms. To help form the map, summarize previous steps concisely based on actual observation (no assumptions); mark the explored and unexplored directions; If one direction is deadend, mark it as deadend and never go there again.
Then, you must choose exactly one of the listed actions and output it strictly in the following format:

<|ACTION|>YOUR_CHOSEN_ACTION<|END|>

Replace YOUR_CHOSEN_ACTION with the chosen action.
Note : The coin is not in the Vault room, which is just an ordinary room.
        """.strip()

cot_instructions_V3 = """
First, think about the best course of action. You should form a 2D map in your head with visited rooms. 
To help form the map, summarize previous steps concisely based on actual observation (no assumptions); mark the explored and unexplored directions; If one direction is deadend, mark it as deadend and never go there again. 
Use the following format for the summary of previous steps. Example:

Step 2 : Room A (Current)
East : explored -> Room B 
West : explored -> Room C (Previous)
North : unexplored
(South : invalid)

Note : if the observation doesn't mention South, it means South direction doesn't exist. You can mark it as invalid, or simpliy avoid mention it in the summary.

Then, you must choose exactly one of the listed actions and output it strictly in the following format:

<|ACTION|>YOUR_CHOSEN_ACTION<|END|>

Replace YOUR_CHOSEN_ACTION with the chosen action.
Note : The coin is not in the Vault room, which is just an ordinary room.
        """.strip()

        # prompting from o3
cot_instructions_o3 = """
You are “Coin-Seeker-R1”, an efficient text-only agent in the TextWorld Coin-Collector game.  
Your goal: find the coin within 80 moves.

──────────────── Strategy ────────────────
1. **Build a mental map.**  
   • Every time you get an observation, extract:
     – `room`  : the room’s name (first line of the description)  
     – `exits` : the list after “Exits:” (N/E/S/W)  
     – `coin?` : whether the word “coin” appears (case-insensitive)  
   • Keep an internal table like  
     `MAP = {room_name: {exits:{N:?,E:?,S:?,W:?}, visited:True}}`  
     A “?” means you haven’t tried that exit yet. You should avoid log a direction doesn't exist in the observation.
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

4. **Output format.**  
   Think silently, but reveal only one lowercase command to the game:
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

cot_instructions_test = """
First, think about the best course of action. You should form a 2D map in your head with visited rooms, marking the explored and unexplored directions.
Keep your thinking short and concise (≤ 60 lines) so you don’t hit token limits.

Then, you must choose exactly one of the listed actions and output it strictly in the following format:

<|ACTION|>YOUR_CHOSEN_ACTION<|END|>

Replace YOUR_CHOSEN_ACTION with the chosen action.
        """.strip()



class RobustCoTAgent_nothink(BaseAgent):
    """An agent that performs actions using a chain-of-thought reasoning process."""

    def __init__(self, client_factory: LLMClientWrapper, prompt_builder, config):
        """Initialize the ChainOfThoughtAgent with a client, prompt builder, and configuration.

        Args:
            client_factory (LLMClientWrapper): A factory for creating the LLM client instance.
            prompt_builder (PromptBuilder): Object to build prompts for the agent.
            config: Configuration object containing settings for the agent.
        """
        super().__init__(client_factory, prompt_builder)
        self.remember_cot = config.agent.remember_cot
        self.use_cot = config.agent.use_cot
        # Create logs directory if it doesn't exist
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

    def act(self, obs, prev_action=None):
        """Generate the next action using chain-of-thought reasoning based on the current observation.

        Args:
            obs (dict): The current observation in the environment.
            prev_action (str, optional): The previous action taken.

        Returns:
            LLMResponse: The response containing the final selected action.
        """
        if prev_action:
            self.prompt_builder.update_action(prev_action)

        self.prompt_builder.update_observation(obs)

        messages = self.prompt_builder.get_prompt()

        cot_instructions = ""

        # Add the updated instructions to the last message
        messages[-1].content += "\n\n" + cot_instructions + (" /no_think" if not self.use_cot else "")

        # Generate the CoT reasoning
        cot_reasoning = self.client.generate(messages)

        # Extract the final answer from the CoT reasoning
        final_answer = self._extract_final_answer(cot_reasoning)

        return final_answer, messages



    def _extract_final_answer(self, reasoning):
        """Extract the final action from the chain-of-thought reasoning response.

        Args:
            reasoning (LLMResponse): The response containing CoT reasoning and action.

        Returns:
            LLMResponse: The response with the extracted final action in `completion`
                         and the entire chain-of-thought in `reasoning`.
        """
        # Make a copy so we don't mutate the original
        final_answer = copy.deepcopy(reasoning)

        # Store the entire chain-of-thought (raw completion) in `reasoning`
        final_answer = final_answer._replace(reasoning=reasoning.completion)

        self.prompt_builder.update_reasoning(reasoning.completion)

        # Now parse the strict action format: <|ACTION|> ... <|END|>
        completion_text = reasoning.completion
        match = re.search(r"<\|ACTION\|>(.*?)<\|END\|>", completion_text, re.DOTALL)
        if match:
            extracted_action = match.group(1).strip()
        else:
            # Fallback to the entire completion if not matched
            extracted_action = "Failed to obtain a valid action from the reasoning."

        # Replace the final `completion` with only the extracted action
        final_answer = final_answer._replace(completion=extracted_action)

        return final_answer
