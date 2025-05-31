from game_loop import play_episode
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Play TextWorld Coin Collector')
    parser.add_argument('--temperature', type=float, default=0.2,
                      help='Temperature for LLM generation (default: 0.2)')
    parser.add_argument('--model', type=str, default="deepseek-reasoner",
                      help='Model to use (default: deepseek-reasoner)')
    parser.add_argument('--base-url', type=str, default="https://api.deepseek.com",
                      help='Base URL for API (default: https://api.deepseek.com)')
    parser.add_argument('--map', type=str, default="tw_games/coin_collector/level_220_seed_1171.ulx",
                      help='Path to the game map file (default: tw_games/coin_collector/level_220_seed_1171.ulx)')
    parser.add_argument('--max-steps', type=int, default=80,
                      help='Maximum number of steps to play (default: 80)')
    
    args = parser.parse_args()
    play_episode(zfile=args.map, max_steps=args.max_steps, temperature=args.temperature, model=args.model, base_url=args.base_url) 