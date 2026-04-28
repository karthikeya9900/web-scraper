from bs4 import BeautifulSoup
import json
import re

# =========================================================
# HELPERS
# =========================================================

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def normalize_player_key(name):
    if not name:
        return None

    name = name.lower()
    name = re.sub(r'[^a-z\s]', '', name)
    name = re.sub(r'\s+', '_', name.strip())

    return name


def resolve_player(name, registry):
    if not name:
        return name

    key = normalize_player_key(name)
    return registry.get(key, {}).get("full_name", name)


def empty_extras():
    return {
        "wides": 0,
        "byes": 0,
        "legbyes": 0,
        "noballs": 0
    }


# =========================================================
# WICKET + FIELDERS
# =========================================================

def detect_wicket_type(text):
    t = text.lower()

    if "bowled" in t:
        return "bowled"
    if "caught" in t or "catch" in t:   # ✅ FIXED BUG
        return "catch"
    if "lbw" in t:
        return "lbw"
    if "run out" in t:
        return "run out"
    if "stumped" in t:
        return "stumped"

    return "unknown"


def extract_fielders(text):
    m = re.search(r'c\s+([A-Za-z\s\.]+?)\s+b', text)
    if m:
        return clean(m.group(1))

    m = re.search(r'st\s+([A-Za-z\s\.]+?)\s+b', text)
    if m:
        return clean(m.group(1))

    m = re.search(r'run out\s*\(([^)]+)\)', text, re.IGNORECASE)
    if m:
        return clean(m.group(1))

    return None


# =========================================================
# PLAYER UTILS
# =========================================================

def generate_aliases(name):
    aliases = set()

    if not name:
        return aliases

    aliases.add(name)

    parts = name.split()
    if len(parts) > 1:
        aliases.add(" ".join([p[0] + "." if i == 0 else p for i, p in enumerate(parts)]))
        aliases.add("".join([p[0] for p in parts if p]))

    return aliases


def clean_player_name(name):
    if not name:
        return None

    name = re.sub(r'\(.*?\)', '', name)
    name = name.split(",")[0]
    name = re.sub(r'\b(PM|AM|WIDE|NB|LB|BYE|OUT|FOUR|SIX)\b.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^A-Za-z\s\.]', '', name)

    return clean(name)


def sanitize_registry(registry):
    return {
        key: {
            "full_name": value["full_name"],
            "aliases": list(value["aliases"])
        }
        for key, value in registry.items()
    }


# =========================================================
# META + TOSS
# =========================================================

def extract_match_meta(soup):
    title = clean(soup.title.string) if soup.title else ""

    if not title:
        return {}

    parts = title.split(" - ")

    return {
        "match": clean(parts[0]) if len(parts) > 0 else "",
        "league": clean(parts[1]) if len(parts) > 1 else ""
    }


def extract_toss_info(soup):
    for el in soup.find_all(string=re.compile("won the toss", re.IGNORECASE)):
        line = clean(el)

        match = re.search(
            r'([A-Za-z\s]+?)\s+won the toss and (elected|chose|opted) to\s+(bat|field|bowl)',
            line,
            re.IGNORECASE
        )

        if match:
            winner = clean(match.group(1))
            decision = match.group(3).lower()

            # safer cleanup (ONLY remove time-like patterns)
            winner = re.sub(r'\b\d{1,2}:\d{2}\s*(AM|PM)?\b', '', winner, flags=re.IGNORECASE)
            winner = clean(winner)

            if decision == "bowl":
                decision = "field"

            return {
                "winner": winner,
                "decision": decision
            }

    return None
# =========================================================
# PLAYER REGISTRY
# =========================================================

def extract_player_registry(soup):
    registry = {}

    for block in soup.select("div.border-b"):
        text = clean(block.get_text(" ", strip=True))

        candidates = []

        if "comes to the crease" in text:
            candidates.append(clean_player_name(text.split("comes")[0]))

        if "comes into the attack" in text:
            candidates.append(clean_player_name(text.split("(")[0]))

        for name in candidates:
            if not name:
                continue

            key = normalize_player_key(name)

            if key not in registry:
                registry[key] = {
                    "full_name": name,
                    "aliases": generate_aliases(name)
                }

    return registry


# =========================================================
# TEAM + ORDER
# =========================================================

def extract_team_name(soup):
    for btn in soup.select("button.ant-dropdown-trigger"):
        text = clean(btn.get_text(" ", strip=True))

        if text not in ["Old", "All", "", "Members", "Clubs", "Matches", "Statistics", "Series", "League"]:
            return text

    return "Unknown"


def order_innings(innings_list, toss_info):
    if not toss_info or len(innings_list) < 2:
        return innings_list

    toss_winner = clean(toss_info["winner"])
    decision = toss_info["decision"]

    team1 = clean(innings_list[0]["team"])
    team2 = clean(innings_list[1]["team"])

    first = toss_winner if decision == "bat" else (team2 if toss_winner == team1 else team1)

    return innings_list if team1 == first else list(reversed(innings_list))


# =========================================================
# CORE PARSING
# =========================================================

def extract_initial_players(soup):
    batsmen = []
    bowler = None

    for block in soup.select("div.border-b"):
        text = clean(block.get_text(" ", strip=True))

        if "comes to the crease" in text:
            name = clean_player_name(text.split("comes")[0])
            if name and name not in batsmen:
                batsmen.append(name)

        if "comes into the attack" in text and not bowler:
            bowler = clean_player_name(text.split("(")[0])

        if len(batsmen) >= 2 and bowler:
            break

    return (
        batsmen[0] if batsmen else None,
        batsmen[1] if len(batsmen) > 1 else None,
        bowler
    )


def extract_players(text):
    m = re.search(r'\d+\.\d+\s+(.*)', text)
    if not m:
        return None, None

    line = m.group(1).split(",")[0]

    if " to " not in line:
        return None, None

    bowler_raw, batter_raw = line.split(" to ")
    return clean_player_name(bowler_raw), clean_player_name(batter_raw)


# =========================================================
# EVENT PARSER (unchanged logic)
# =========================================================

def parse_event(full_text, batter_name, is_wicket):
    t = full_text.lower()

    runs = {"batter": 0, "extras": 0, "total": 0}
    extras = empty_extras()
    wickets = []

    if is_wicket:
        wickets.append({
            "kind": detect_wicket_type(t),
            "player_out": batter_name,
            "fielders": extract_fielders(full_text)
        })

    if "wide" in t:
        extras["wides"] = 1
        runs["extras"] = 1
        runs["total"] = 1
        return runs, extras, wickets, False

    if "no ball" in t:
        extras["noballs"] = 1
        runs["extras"] = 1
        runs["total"] = 1
        return runs, extras, wickets, False

    if "four" in t:
        runs["batter"] = 4
    elif "six" in t:
        runs["batter"] = 6
    else:
        nums = re.findall(r'\d+', full_text)
        if nums:
            runs["batter"] = int(nums[0])

    runs["total"] = runs["batter"]

    return runs, extras, wickets, True


# =========================================================
# HTML PARSER
# =========================================================

def parse_html(file_path, registry):
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    team_name = extract_team_name(soup)
    striker, non_striker, _ = extract_initial_players(soup)

    striker = resolve_player(striker, registry)
    non_striker = resolve_player(non_striker, registry)

    overs = {}

    for node in soup.select("div.border-b"):
        text = clean(node.get_text(" ", strip=True))

        match = re.search(r'(\d+)\.(\d+)', text)
        if not match:
            continue

        over_id, ball_id = match.groups()

        bowler, batter = extract_players(text)
        if not bowler or not batter:
            continue

        bowler = resolve_player(bowler, registry)
        batter = resolve_player(batter, registry)

        runs, extras, wickets, _ = parse_event(text, batter, "OUT!" in text)

        delivery = {
            "ball": f"{over_id}.{ball_id}",
            "batter": striker,
            "bowler": bowler,
            "non_striker": non_striker,
            "runs": runs
        }

        if any(extras.values()):
            delivery["extras"] = extras

        if wickets:
            delivery["wickets"] = wickets

        overs.setdefault(over_id, []).append(delivery)

    return {
        "team": team_name,
        "overs": [
            {"over": o, "deliveries": d}
            for o, d in sorted(overs.items(), key=lambda x: int(x[0]))
        ]
    }


# =========================================================
# PUBLIC API
# =========================================================

def generate_match_json(files, output_file=None):
    match_context = {
        "meta": {},
        "toss": None,
        "teams": set(),
        "player_registry": {},
        "innings_raw": []
    }

    # =========================================================
    # PASS 1 → Scan ALL files for meta, registry, toss
    # =========================================================
    for file_path in files:
        print(f"🔍 Scanning {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        # meta (only once)
        if not match_context["meta"]:
            match_context["meta"] = extract_match_meta(soup)

        # registry (only once)
        if not match_context["player_registry"]:
            match_context["player_registry"] = extract_player_registry(soup)

        # 🔥 IMPORTANT: check toss in EVERY file
        if match_context["toss"] is None:
            toss = extract_toss_info(soup)
            if toss:
                print(f"✅ Toss found in {file_path}: {toss}")
                match_context["toss"] = toss

    # =========================================================
    # PASS 2 → Parse innings
    # =========================================================
    for file_path in files:
        innings = parse_html(file_path, match_context["player_registry"])
        match_context["teams"].add(innings["team"])
        match_context["innings_raw"].append(innings)

    result = {
        "meta": match_context["meta"],
        "toss": match_context["toss"] or {
            "winner": "Unknown",
            "decision": "Unknown"
        },
        "teams": list(match_context["teams"]),
        "player_registry": sanitize_registry(match_context["player_registry"]),
        "innings": order_innings(match_context["innings_raw"], match_context["toss"])
    }

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    return result

# =========================================================
# CLI RUN (OPTIONAL)
# =========================================================

if __name__ == "__main__":
    files = ["innings_1.html", "innings_2.html"]
    generate_match_json(files, "output.json")
    print("✅ JSON generated")