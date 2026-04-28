from bs4 import BeautifulSoup
import json
import re


# ---------------- HELPERS ----------------

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def empty_extras():
    return {
        "wides": 0,
        "byes": 0,
        "legbyes": 0,
        "noballs": 0
    }


# ---------------- PLAYER NORMALIZATION (PHASE 3 CORE FIX) ----------------

def normalize_player_key(name):
    if not name:
        return None

    name = name.lower()
    name = re.sub(r'[^a-z\s]', '', name)
    name = re.sub(r'\s+', '_', name.strip())

    return name


def generate_aliases(name):
    aliases = set()

    if not name:
        return aliases

    aliases.add(name)

    parts = name.split()

    # initials format
    if len(parts) > 1:
        aliases.add(" ".join([p[0] + "." if i == 0 else p for i, p in enumerate(parts)]))
        aliases.add("".join([p[0] for p in parts if p]))

    return aliases


# ---------------- PLAYER CLEANING ----------------

def sanitize_registry(registry):
    clean_registry = {}

    for key, value in registry.items():
        clean_registry[key] = {
            "full_name": value["full_name"],
            "aliases": list(value["aliases"])  # 🔥 FIX HERE
        }

    return clean_registry

def clean_player_name(name):
    if not name:
        return None

    name = re.sub(r'\(.*?\)', '', name)
    name = name.split(",")[0]
    name = re.sub(r'\b(PM|AM|WIDE|NB|LB|BYE|OUT|FOUR|SIX)\b.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^A-Za-z\s\.]', '', name)

    return clean(name)


# ---------------- META ----------------

def extract_match_meta(soup):
    meta = {}

    # safest source
    title = soup.title.string if soup.title else ""
    title = clean(title)

    if not title:
        return meta

    # split match vs league using " - "
    parts = title.split(" - ")

    # -----------------------
    # 1. MATCH PART (teams)
    # -----------------------
    if len(parts) >= 1:
        match_part = parts[0].strip()
        meta["match"] = clean(match_part)

    # -----------------------
    # 2. LEAGUE PART (tournament)
    # -----------------------
    if len(parts) >= 2:
        league_part = parts[1].strip()
        meta["league"] = clean(league_part)

    return meta

# ---------------- TOSS ----------------

def extract_toss_info(soup):
    text = soup.get_text(" ", strip=True)

    match = re.search(
        r'([A-Za-z0-9\s]+) won the toss and elected to (bat|field|bowl)',
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    winner = clean(re.sub(r'^\d+\s*(AM|PM)?\s*', '', match.group(1)))
    decision = match.group(2).lower()

    if decision == "bowl":
        decision = "field"

    return {
        "winner": winner,
        "decision": decision
    }


# ---------------- PLAYER REGISTRY (FIXED PHASE 3 VERSION) ----------------

def extract_player_registry(soup):
    registry = {}

    blocks = soup.select("div.border-b")

    for block in blocks:
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


# ---------------- TEAM ----------------

def extract_team_name(soup):
    buttons = soup.select("button.ant-dropdown-trigger")

    for btn in buttons:
        text = clean(btn.get_text(" ", strip=True))

        if text in ["Old", "All", ""]:
            continue

        if text in ["Members", "Clubs", "Matches", "Statistics", "Series", "League"]:
            continue

        return text

    return "Unknown"


# ---------------- INNINGS ORDERING ----------------

def order_innings(innings_list, toss_info):
    if not toss_info or len(innings_list) < 2:
        return innings_list

    toss_winner = clean(toss_info["winner"])
    decision = toss_info["decision"]

    team1 = clean(innings_list[0]["team"])
    team2 = clean(innings_list[1]["team"])

    if decision == "bat":
        first_batting = toss_winner
    else:
        first_batting = team2 if toss_winner == team1 else team1

    return innings_list if team1 == first_batting else list(reversed(innings_list))


# ---------------- INITIAL PLAYERS ----------------

def extract_initial_players(soup):
    batsmen = []
    bowler = None

    blocks = soup.select("div.border-b")

    for block in blocks:
        text = clean(block.get_text(" ", strip=True))

        if "comes to the crease" in text:
            name = clean_player_name(text.split("comes")[0])
            if name and name not in batsmen:
                batsmen.append(name)

        if "comes into the attack" in text and bowler is None:
            bowler = clean_player_name(text.split("(")[0])

        if len(batsmen) >= 2 and bowler:
            break

    striker = batsmen[0] if batsmen else None
    non_striker = batsmen[1] if len(batsmen) > 1 else None

    return striker, non_striker, bowler


# ---------------- PLAYER PARSER ----------------

def extract_players(text):
    m = re.search(r'\d+\.\d+\s+(.*)', text)
    if not m:
        return None, None

    line = m.group(1).split(",")[0]

    if " to " not in line:
        return None, None

    bowler_raw, batter_raw = line.split(" to ")

    return clean_player_name(bowler_raw), clean_player_name(batter_raw)


# ---------------- EVENT PARSER ----------------

def parse_event(full_text, batter_name, is_wicket):
    t = full_text.lower()

    runs = {"batter": 0, "extras": 0, "total": 0}
    extras = empty_extras()
    wickets = []

    if is_wicket:
        wickets.append({
            "kind": "unknown",
            "player_out": batter_name,
            "fielders": None
        })
        return runs, extras, wickets, True

    if "wide" in t:
        extras["wides"] = 1
        runs["extras"] = 1
        runs["total"] = 1
        return runs, extras, wickets, False

    if "bye" in t:
        extras["byes"] = 1
        runs["extras"] = 1
        runs["total"] = 1
        return runs, extras, wickets, True

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


# ---------------- INNINGS PARSER ----------------

def parse_html(file_path):

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    team_name = extract_team_name(soup)
    balls = soup.select("div.border-b")

    overs = {}

    striker, non_striker, current_bowler = extract_initial_players(soup)

    for node in balls:
        text = clean(node.get_text(" ", strip=True))

        match = re.search(r'(\d+)\.(\d+)', text)
        if not match:
            continue

        over_id, ball_id = match.groups()

        bowler, batter = extract_players(text)
        if not bowler or not batter:
            continue

        is_wicket = "OUT!" in text

        runs, extras, wickets, legal = parse_event(text, striker, is_wicket)

        delivery = {
            "ball": f"{over_id}.{ball_id}",
            "batter": striker,
            "bowler": bowler,
            "non_striker": non_striker,
            "runs": runs
        }

        if wickets:
            delivery["wickets"] = wickets

        overs.setdefault(over_id, []).append(delivery)

        if legal and runs["batter"] % 2 == 1:
            striker, non_striker = non_striker, striker

        if wickets:
            striker = None

    return {
        "team": team_name,
        "overs": [
            {"over": o, "deliveries": d}
            for o, d in sorted(overs.items(), key=lambda x: int(x[0]))
        ]
    }


# ---------------- MATCH PARSER ----------------

def parse_match(files):

    match_context = {
        "meta": {},
        "toss": None,
        "teams": set(),
        "player_registry": {},
        "innings_raw": []
    }

    for idx, file_path in enumerate(files):

        print(f"📄 Parsing {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        if idx == 0:
            match_context["meta"] = extract_match_meta(soup)
            match_context["player_registry"] = extract_player_registry(soup)

        if match_context["toss"] is None:
            match_context["toss"] = extract_toss_info(soup)

        innings = parse_html(file_path)
        match_context["teams"].add(innings["team"])
        match_context["innings_raw"].append(innings)

    ordered = order_innings(match_context["innings_raw"], match_context["toss"])

    return {
        "meta": match_context["meta"],
        "toss": match_context["toss"],
        "teams": list(match_context["teams"]),
        "player_registry": sanitize_registry(match_context["player_registry"]),
        "innings": ordered
    }


# ---------------- RUN ----------------

match_files = ["innings_1.html", "innings_2.html"]

data = parse_match(match_files)

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("✅ Phase 3 complete: Structured cricket dataset generated")