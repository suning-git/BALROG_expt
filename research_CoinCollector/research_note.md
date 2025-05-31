This fork use BALROG's framework to understand LLM's ability to play TextWorld CoinCollector.

## Changes and usage
### Changes
* Support deepseek
* Visualize CoinCollector Map and game trajectory
* Add prompts to instruct LLM to use DFS to play the game
### Usage

Set API KEY first.

Example for deepseek-r1:
```
python eval.py \
  agent.type=robust_cot_nothink \
  agent.max_image_history=0 \
  eval.num_workers=5 \
  client.client_name=openai \
  client.base_url=https://api.deepseek.com \
  client.model_id=deepseek-reasoner \
  client.alternate_roles=True \
  envs.textworld_kwargs.max_episode_steps=100 \
  agent.max_text_history=100 \
  agent.use_cot=True \
  agent.max_cot_history=100 \
  eval.num_episodes.textworld=5 \
  client.generate_kwargs.temperature=0.2
```

Example for o3-mini:

```
python eval.py \
  agent.type=robust_cot_nothink \
  agent.max_image_history=0 \
  eval.num_workers=1 \
  client.client_name=openai \
  client.base_url=https://api.openai.com/v1 \
  client.model_id=o3-mini \
  client.alternate_roles=True \
  envs.textworld_kwargs.max_episode_steps=100 \
  agent.max_text_history=100 \
  agent.use_cot=True \
  agent.max_cot_history=100 \
  eval.num_episodes.textworld=1
```

Visualization for the game map:
```
python ./tw_games/cc_vis_V0.py ./tw_games/coin_collector/level_220_seed_1171.json
```

Visualization for the game map + LLM path:
```
python ./tw_games/cc_vis_V0.py ./tw_games/coin_collector/level_220_seed_1171.json --path ./results/2025-05-25_00-26-11_robust_cot_nothink_o3-mini/textworld/coin_collector/coin_collector_run_00.csv
```


# Research status

## Benchmark LLM with DFS prompts

The maps in tw_games/coin_collector/ are more or less linear. Typical map looks like this

level_220_seed_1171:
![image](https://hackmd.io/_uploads/rJlAuUzfgg.png)

This task is trivial for human. Surprisingly, all LLMs couldn't do it. In below, all runs use level_220_seed_1171. Examples runs:

o3-mini:
![image](https://hackmd.io/_uploads/ryoD_wzzlx.png)

Qwen3:
![image](https://hackmd.io/_uploads/SJQcdDzflg.png)

R1:
![image](https://hackmd.io/_uploads/SJGsODGfeg.png)

LLM often start to make mistakes after 20 steps, and never be able to recover from the mistake. 

I tried to ask the LLM to write a prompt to outline the strategy to guide the LLM to play the game. This doesn't work well. In general the LLM won't be able to follow strategy and make too many mistakes.

I wrote a stronger prompt that prevent various common LLM mistakes. The prompts is `coin_collector_instruction_V4` in balrog\environments\textworld\__init__.py   

With this prompts : r1 has 50% success rate; o3-mini 0%

Example: a successful run with r1:
![image](https://hackmd.io/_uploads/HknDiEMMxx.png)

Example: a failed run with r1:
![image](https://hackmd.io/_uploads/SyQoiNGflx.png)

Example: a failed run with o3-mini:
![image](https://hackmd.io/_uploads/rk5poNzGxe.png)
Note: o3-mini

Some mistakes made by LLM are in `research_CoinCollector\LLM_mistakes`

Observations and thoughts:
* When the context become too long, LLM start to abbreviate the map log (even being told not to) and lose rigor. It seems LLM can't do careful logical operation over long context. I heard that in long context, LLM often focus on the beginning and the ending part. But this cannot explain the observations in this test, because here LLM only need dialog from the last step to act correctly. 
* In some cases, LLM COT really noticed a mistake and thought about it and in the end still made the mistake. Human will not behave in this way.
* Even if the LLM could exactly follow my instruction every time and win the game with 100%, it's not really a success. The true success should be : ask the LLM to come up with a strategy (ideally similar to the prompt I wrote), and follow the strategy to play the game.
* There are two separate topics for LLM : 1, understand the general strategy / playbook, and act in a highly responsible manner. The task is not necessary complex (such as simple maze), but the performance has to be absolutely correct; 2, graph reasoning (even though the input is purely text). Coin Collector is ideal test for these topics.


## Agent mode with memory
05/30/2025: I wrote a standalone agent (doesn't require BALROG) with external memory. See research_CoinCollector/AgentCC. The agent use OpenAI API to call "tools" to interact with the game and the memory.

Usages: 
To run a game with specific map and temperature:
```
python ./main.py --temperature 0 --model deepseek-chat --map ./tw_games/coin_collector_level300/level_300_seed_0.ulx  --max-steps 200
```
To visualize the maze and agent path:
```
python cc_vis_V2.py ./tw_games/coin_collector/level_220_seed_1171.json --path ./results/play_dschat_t0_L300_LOSS_run1.csv
```

### More experiments

I realize the temperature is a crucial factor here. Even T=0.2 is too high. Changing to T=0 increases the logical rigor. 

At T=0, I did various experiments: with detailed DFS operational guideline; no operational detail but give hint to use DFS; no mention DFS at all.

For the first time, deepseek-chat could win the game only with a hint of DFS. The system prompts is `LLM_system_prompt_V1` in llm_interface.py. Result: `play_dschat_t0_DFShint_WIN.csv` . Note the LLM doesn't intensively use the agent memory.
Note: I tried the same for Qwen3, failed.

With no hint of DFS, deepseek-chat fail in very early stage:
![image](https://hackmd.io/_uploads/Sk9CXh_Mee.png)

From now on, until we test for graph reasoning, we should at least give hint of DFS or full operational guideline.

At T=0, with detailed DFS operational guideline (adopted from `coin_collector_instruction_V4` in previous section), deepseek-chat can't solve larger maze (coin collector level 300 difficulty). See play_dschat_t0_L300_LOSS_run1.csv

![image](https://hackmd.io/_uploads/HyIKIhdGex.png)


Summary and thoughts:

With DSF operational guideline:
As T->0 the logical rigor is in general better and the LLM could proceed longer in the maze.
The logical rigor get worse as the context gets longer. Just give agent memory won't solve this issue. 

To try next: modify the way the agent use the memory. Agent should always start with the "state-of-the-mind" summary of what happened, not the dialog text. But it will have access to the full dialog text when needed. The system prompt should teach the LLM how to operate in this mode.
