import time
import datetime
import networkx as nx
import requests
import community as community_louvain
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt

ARCTIC_BASE = "https://arctic-shift.photon-reddit.com"
HEADERS = {"User-Agent": "Lattice/1.0 (subreddit graph builder)"}
PAGE_SIZE = 100
MAX_PAGES = 50
PAGE_DELAY = 2.0  # Increased delay between requests
MAX_RETRIES = 5   # Retries for 422 rate-limit errors


def _fetch_comments_paginated(subreddit: str, target: int) -> list[dict]:
    import time
    collected = []
    before_ts = None

    for page in range(MAX_PAGES):
        params = {
            "subreddit": subreddit,
            "limit": PAGE_SIZE,
            "sort": "desc",
        }
        if before_ts is not None:
            # Clamp to now to prevent future date 500 errors
            safe_ts = min(int(before_ts), int(time.time()))
            params["before"] = safe_ts

        retries = 0
        while retries < 3:
            try:
                resp = requests.get(
                    f"{ARCTIC_BASE}/api/comments/search",
                    params=params,
                    headers=HEADERS,
                    timeout=30,
                )
                if resp.status_code == 500:
                    print("  Arctic Shift 500 Error (likely bad timestamp). Stopping early.")
                    return collected[:target]
                if resp.status_code == 422:
                    print("  Server requested slow down (422). Waiting 2s...")
                    time.sleep(2)
                    retries += 1
                    continue
                
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                print(f"  Request error: {e}")
                retries += 1
                if retries >= 3:
                    return collected[:target]
                time.sleep(2)

        data = resp.json().get("data", [])
        if not data:
            break

        collected.extend(data)
        print(f"  Page {page + 1}: fetched {len(data)} comments (total {len(collected)})")

        if len(collected) >= target:
            break

        before_ts = data[-1]["created_utc"]
        time.sleep(1.5)

    return collected[:target]



def _build_graph_from_comments(comments: list[dict]) -> nx.DiGraph:
    g = nx.DiGraph()
    id_to_author = {}

    for c in comments:
        author, cid = c.get("author"), c.get("id")
        if author and author != "[deleted]" and cid:
            id_to_author[cid] = author

    for c in comments:
        author = c.get("author")
        if not author or author == "[deleted]":
            continue

        if not g.has_node(author):
            g.add_node(author, message_count=0, score=0, subreddit=c.get("subreddit"))
        g.nodes[author]["message_count"] += 1
        g.nodes[author]["score"] += c.get("score", 0)

        parent = c.get("parent_id") or ""
        if parent.startswith("t1_"):
            parent_author = id_to_author.get(parent[3:])
            if parent_author and parent_author != author:
                if not g.has_node(parent_author):
                    g.add_node(parent_author, message_count=0, score=0,
                               subreddit=c.get("subreddit"))
                w = g.get_edge_data(parent_author, author, {}).get("weight", 0)
                g.add_edge(parent_author, author, weight=w + 1)

    undirected = g.to_undirected()
    try:
        partition = community_louvain.best_partition(undirected)
        communities = set(partition.values())
        cmap = plt.get_cmap("tab20")
        colors = {c: mcolors.to_hex(cmap(i / max(1, len(communities))))
                  for i, c in enumerate(communities)}
        for node, comm_id in partition.items():
            g.nodes[node]["group"] = comm_id
            g.nodes[node]["color"] = colors[comm_id]
    except Exception as e:
        print(f"Community detection failed: {e}")

    return g


def load_subreddit(subreddit: str, limit: int = 1000):
    comments = _fetch_comments_paginated(subreddit, target=limit)
    g = _build_graph_from_comments(comments)


    # --------------------------------------------------


    # Prune sparse leaf nodes to prevent the ring layout


    meta = {
        "source": "arctic-shift",
        "subreddit": subreddit,
        "requested": limit,
        "fetched": len(comments),
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
    }
    
    # --- CO-POST EDGES: users who commented on the same Reddit post ---
    from collections import defaultdict
    post_to_users = defaultdict(set)
    for cm in comments:
        author = cm.get("author")
        link_id = cm.get("link_id")
        if author and author != "[deleted]" and link_id:
            post_to_users[link_id].add(author)
    for link_id, users in post_to_users.items():
        if len(users) < 2:
            continue
        # Cap group size to avoid O(n^2) explosions on mega-posts
        users = list(users)[:30]
        for i, u in enumerate(users):
            for v in users[i+1:]:
                if g.has_node(u) and g.has_node(v) and u != v:
                    w = g.get_edge_data(u, v, {}).get("weight", 0)
                    g.add_edge(u, v, weight=w + 1,
                               edge_type="co_post",
                               positive_count=g.get_edge_data(u, v, {}).get("positive_count", 0),
                               negative_count=g.get_edge_data(u, v, {}).get("negative_count", 0),
                               message_count=g.get_edge_data(u, v, {}).get("message_count", 1))
    # ---------------------------------------------------------------

    
    # --- CO-THREAD EDGES (Dense Galaxy) ---
    from collections import defaultdict
    thread_users = defaultdict(set)
    for cm in comments:
        author = cm.get("author")
        link_id = cm.get("link_id")
        if author and author != "[deleted]" and link_id:
            thread_users[link_id].add(author)
            
    for link_id, users in thread_users.items():
        if len(users) < 2: continue
        users = list(users)[:50] # Cap at 50 users per thread to avoid O(n^2) explosion
        for i, u in enumerate(users):
            for v in users[i+1:]:
                if g.has_node(u) and g.has_node(v) and u != v:
                    w = g.get_edge_data(u, v, {}).get("weight", 0)
                    g.add_edge(u, v, weight=w + 1,
                               positive_count=g.get_edge_data(u, v, {}).get("positive_count", 0),
                               negative_count=g.get_edge_data(u, v, {}).get("negative_count", 0),
                               message_count=g.get_edge_data(u, v, {}).get("message_count", 1))
    # --------------------------------------

    
    # --- CO_THREAD_EDGES ---
    from collections import defaultdict
    thread_users = defaultdict(set)
    for cm in comments:
        author = cm.get("author")
        link_id = cm.get("link_id")
        if author and author != "[deleted]" and link_id:
            thread_users[link_id].add(author)
            
    for link_id, users in thread_users.items():
        if len(users) < 2: continue
        users = list(users)[:50]
        for i, u in enumerate(users):
            for v in users[i+1:]:
                if g.has_node(u) and g.has_node(v) and u != v:
                    w = g.get_edge_data(u, v, {}).get("weight", 0)
                    g.add_edge(u, v, weight=w + 1,
                               positive_count=g.get_edge_data(u, v, {}).get("positive_count", 0),
                               negative_count=g.get_edge_data(u, v, {}).get("negative_count", 0),
                               message_count=g.get_edge_data(u, v, {}).get("message_count", 1))
    # ----------------------

    return g, meta
