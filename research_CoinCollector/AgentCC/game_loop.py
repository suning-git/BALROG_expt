import json
import logging
import datetime
from typing import List, Dict
from pathlib import Path
from openai import OpenAI

from agent_os import AgentOS
from llm_interface import next_model_message, create_client, bootstrap_prompt

def handle_tool_call(tool_call: dict, agent_os: AgentOS, message_content: str) -> dict:
    """
    Execute a tool call and return the appropriate response.
    
    This function processes the tool call and executes the corresponding
    action through the AgentOS interface.
    
    Args:
        tool_call: The tool call to execute
        agent_os: The AgentOS instance
        message_content: The content of the message that triggered this tool call
    """
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)
    
    if function_name == "read_memory":
        key = arguments["key"]
        value = agent_os.read_memory(key)
        print(f"read_memory: '{key}': {value}")
        agent_os.log_to_csv(f"read_memory({key})", value, message_content)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": function_name,
            "content": json.dumps({"value": value})
        }

    elif function_name == "write_memory":
        key = arguments["key"]
        value = arguments["value"]
        agent_os.write_memory(key, value)
        print(f"write_memory: '{key}': {value}")
        agent_os.log_to_csv(f"write_memory({key})", value, message_content)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": function_name,
            "content": json.dumps({"status": "success"})
        }

    elif function_name == "game_action":
        old_room = agent_os.current_room
        action = arguments["action"]
        obs = agent_os.execute_game_action(action)
        print(f"game_action: {action} : {obs}")
        agent_os.log_to_csv(f"game_action({action})", obs, message_content, old_room)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": function_name,
            "content": json.dumps({"observation": obs})
        }
    
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "name": function_name,
        "content": json.dumps({"error": f"Unknown tool: {function_name}"})
    }

def process_model_message(msg: dict, agent_os: AgentOS) -> List[dict]:
    """
    Process a model message containing tool calls and return response messages.
    
    This function:
    1. Extracts tool calls from the message
    2. Executes each tool call through AgentOS
    3. Returns the responses as a list of messages
    """
    if not msg.tool_calls:
        return []
    
    response_messages = []
    for tool_call in msg.tool_calls:
        response = handle_tool_call(tool_call, agent_os, msg.content)
        response_messages.append(response)
    
    return response_messages

def play_episode(
    zfile: str = "tw_games/coin_collector/level_220_seed_1171.ulx",
    max_steps: int = 80,
    *,
    client: OpenAI | None = None,
    temperature: float = 0.2,
    model: str = "deepseek-reasoner",
    base_url: str = "https://api.deepseek.com",
):
    """
    Main control loop for playing one episode of the game.
    
    The loop:
    1. Gets the next action from the LLM
    2. Processes any tool calls in the response
    3. Updates the game state
    4. Continues until the episode is done or max steps reached
    
    Args:
        zfile: Path to the game file
        max_steps: Maximum number of steps to play
        client: OpenAI client instance (optional)
        temperature: Temperature for LLM generation
        model: Model to use for generation
        base_url: Base URL for the API
    """
    # Set up logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(__file__).parent / "results" / f"log_{timestamp}.txt"
    csv_file = Path(__file__).parent / "results" / f"play_{timestamp}.csv"
    
    # Create results directory if it doesn't exist
    (Path(__file__).parent / "results").mkdir(exist_ok=True)
    
    logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    client = client or create_client(base_url=base_url)
    agent_os = AgentOS(zfile, max_steps, csv_file)
    messages = bootstrap_prompt(agent_os.current_obs)

    while agent_os.step_count < max_steps:
        logging.info(f"\nStep {agent_os.step_count}:\nMessages: {str(messages)}")
        
        msg = next_model_message(client, messages, temperature=temperature, model=model)
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
        
        # Process any tool calls in the message
        response_messages = process_model_message(msg, agent_os)
        messages.extend(response_messages)
        
        print(f"[{agent_os.step_count:02d}] Agent → {msg.content}")
        
        # Check if the episode is done
        if agent_os.done:
            print("🎉 Episode finished!")
            break 