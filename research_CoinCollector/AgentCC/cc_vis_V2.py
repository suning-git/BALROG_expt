#!/usr/bin/env python3
"""
visualize_textworld_map_friendly.py

Draws a TextWorld map with human-readable room names (Bathroom, Bedroom…)
instead of the internal IDs (r_1, r_2).

Usage
-----
python visualize_textworld_map_friendly.py level_220_seed_100.json        # show in a window
python visualize_textworld_map_friendly.py level_220_seed_100.json --out coin_map.png
                                                                           # save to PNG
python visualize_textworld_map_friendly.py level_220_seed_100.json --csv path.csv  # show with path

Dependencies
------------
pip install networkx matplotlib
(TextWorld itself is **not** required – we parse the JSON directly.)
"""
import json, argparse
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import csv
import re
import random


csv.field_size_limit(100000000)

# Predicate → (label forward, label reverse)
DIR_FACTS = {
    "north_of": ("N", "S"),
    "south_of": ("S", "N"),
    "east_of":  ("E", "W"),
    "west_of":  ("W", "E"),
}

# ---------------------------------------------------------------------------

def load_room_names(infos_section):
    """
    Return a dict  {room_id -> pretty_name}
    The pretty name is taken from info["name"] (e.g. "bathroom") and title-cased.
    """
    names = {}
    reverse_names = {}  # Add reverse mapping
    for obj_id, obj_info in infos_section:
        if obj_info.get("type") == "r":
            raw = obj_info.get("name") or obj_id          # fall back to r_* if absent
            pretty_name = raw.replace("_", " ").title()   # "bathroom" → "Bathroom"
            names[obj_id] = pretty_name
            reverse_names[pretty_name] = obj_id           # Store reverse mapping
    return names, reverse_names

def build_graph(world_facts):
    """Convert the directional facts into a NetworkX DiGraph."""
    G = nx.DiGraph()
    coin_room = None
    
    for fact in world_facts:
        key = fact["name"]
        if key == "at" and fact["arguments"][0]["name"] == "o_0":  # o_0 is the coin
            coin_room = fact["arguments"][1]["name"]
        elif key in DIR_FACTS:
            a = fact["arguments"][0]["name"]
            b = fact["arguments"][1]["name"]
            fwd, rev = DIR_FACTS[key]
            G.add_edge(a, b, dir=fwd)
            G.add_edge(b, a, dir=rev)
    return G, coin_room

def draw_path(G, pos, path, reverse_names, jitter=0.02):
    """
    Draw the path on the graph with small random variations in positions.
    
    Args:
        G: NetworkX graph
        pos: Dictionary of node positions
        path: List of room names in the path
        reverse_names: Dictionary mapping room names to room IDs
        jitter: Amount of random variation to add to positions
    """
    # Convert path of room names to list of coordinates
    path_coords = []
    for node_name in path:
        node_id = reverse_names.get(node_name)
        if node_id and node_id in pos:
            path_coords.append(pos[node_id])
    
    if len(path_coords) < 2:
        return

    # Create slightly varied coordinates for the path
    varied_coords = []
    for i, coord in enumerate(path_coords):
        x, y = coord
        # Add small random variation
        varied_coords.append((
            x + random.uniform(-jitter, jitter),
            y + random.uniform(-jitter, jitter)
        ))

    # Create edges from the varied coordinates
    path_edges = list(zip(varied_coords[:-1], varied_coords[1:]))
    
    # Draw the path
    if path_edges:
        # Generate a random color
        color = f'#{random.randint(0, 0xFFFFFF):06x}'
        
        # Draw each edge of the path
        for (x1, y1), (x2, y2) in path_edges:
            plt.plot([x1, x2], [y1, y2], 
                    color=color, 
                    linewidth=2, 
                    alpha=0.7,
                    solid_capstyle='round')
            
            # Draw arrow at the end of each segment
            dx = x2 - x1
            dy = y2 - y1
            plt.arrow(x1, y1, dx*0.8, dy*0.8,
                     head_width=0.01,
                     head_length=0.01,
                     fc=color,
                     ec=color,
                     alpha=0.7,
                     length_includes_head=True)

def draw(G, room_names, reverse_names, path=None, outfile=None, coin_room=None):
    pos    = nx.spring_layout(G, seed=42)   # quick automatic layout
    labels = {n: room_names.get(n, n) for n in G.nodes}

    # Draw the base graph
    nx.draw(G, pos, labels=labels, node_size=0, font_size=8)

    # Highlight coin room if it exists
    if coin_room:
        nx.draw_networkx_nodes(G, pos, 
                             nodelist=[coin_room],
                             node_color='gold',
                             node_size=100,
                             alpha=0.7)

    # Draw the path if provided
    if path:
        draw_path(G, pos, path, reverse_names)

    if outfile:
        plt.savefig(outfile, bbox_inches="tight", dpi=300)
        print(f"Saved map to {outfile}")
    else:
        plt.show()

# ---------------------------------------------------------------------------



def extract_path_from_csv(filename):
    """
    Extracts room names from the Room column of the CSV file.
    Removes consecutive duplicate room names to get the actual path.
    
    :param filename: Path to the CSV file.
    :return: List of room names in the order they were visited, with consecutive duplicates removed.
    """
    results = []
    last_room = None
    
    with open(filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            current_room = row['Room']
            # Only add the room if it's different from the last one
            if current_room != last_room:
                results.append(current_room)
                last_room = current_room
    
    return results

def main():
    ap = argparse.ArgumentParser(description="Visualise a TextWorld map with friendly room names.")
    ap.add_argument("json_file", type=Path, help="compiled *.json* file")
    ap.add_argument("--out", metavar="PNG", help="write figure to PNG instead of showing it")
    ap.add_argument("--path", metavar="CSV", help="CSV file containing the path to visualize")
    args = ap.parse_args()

    data        = json.loads(args.json_file.read_text())
    room_names, reverse_names  = load_room_names(data["infos"])
    G, coin_room = build_graph(data["world"])
    
    path = None
    if args.path:
        path = extract_path_from_csv(args.path)

    print(f"Path: {path}")
    
    draw(G, room_names, reverse_names, path=path, outfile=args.out, coin_room=coin_room)

if __name__ == "__main__":
    main()
