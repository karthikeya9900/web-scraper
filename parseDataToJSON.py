from bs4 import BeautifulSoup
import json
import re


# ---------------- HELPERS ----------------

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def is_valid_name(name):
    return len(name.split()) <= 3 and len(name) < 40


# ---------------- NAME MAP ----------------

def build_name_map(soup):
    name_map = {}
    blocks = soup.select("div.border-b")

    for block in blocks:
        text = clean(block.get_text(" ", strip=True))

        if "comes to the crease" in text:
            full_name = clean(text.split("(")[0])
            parts = full_name.split()

            if len(parts) >= 2:
                short_name = " ".join(parts[:2])
                name_map[short_name] = full_name

    return name_map


# ---------------- INITIAL PLAYERS ----------------

def extract_initial_players(soup):
    striker = None
    non_striker = None
    bowler = None

    blocks = soup.select("div.border-b")

    for block in blocks:
        text = clean(block.get_text(" ", strip=True))

        if "comes to the crease" in text:
            name = clean(text.split("(")[0])
            if is_valid_name(name):
                if not striker:
                    striker = name
                elif not non_striker:
                    non_striker = name

        elif "comes into the attack" in text:
            name = clean(text.split("(")[0])
            if is_valid_name(name):
                bowler = name

        if striker and non_striker and bowler:
            break

    return striker, non_striker, bowler


# ---------------- EVENT PARSER ----------------

def parse_event(outcome, batter_name, is_wicket=False):
    outcome_l = outcome.lower()

    runs = {"batter": 0, "extras": 0, "total": 0}
    extras = {}
    wickets = []

    # ---------------- WICKET ----------------
    if is_wicket:
        kind = "unknown"
        fielders = []

        if "bowled" in outcome_l:
            kind = "bowled"

        elif "caught" in outcome_l:
            kind = "caught"
            f = re.findall(r'c\s+([A-Za-z\s]+)', outcome)
            if f:
                fielders.append({"name": clean(f[0])})

        elif "run out" in outcome_l:
            kind = "run out"
            f = re.findall(r'\((.*?)\)', outcome)
            if f:
                fielders.append({"name": clean(f[0])})

        wickets.append({
            "kind": kind,
            "player_out": batter_name,
            "fielders": fielders if fielders else None
        })

        return runs, extras, wickets

    # ---------------- WIDES ----------------
    if "wide" in outcome_l or "wd" in outcome_l:
        val = int(re.findall(r'\d+', outcome)[0]) if re.findall(r'\d+', outcome) else 1
        extras["wides"] = val
        runs["extras"] = val
        runs["total"] = val
        return runs, extras, wickets

    # ---------------- LEG BYES ----------------
    if "lb" in outcome_l:
        val = int(re.findall(r'\d+', outcome)[0]) if re.findall(r'\d+', outcome) else 1
        extras["legbyes"] = val
        runs["extras"] = val
        runs["total"] = val
        return runs, extras, wickets

    # ---------------- BYES ----------------
    if re.search(r'\bb\b', outcome_l):
        val = int(re.findall(r'\d+', outcome)[0]) if re.findall(r'\d+', outcome) else 1
        extras["byes"] = val
        runs["extras"] = val
        runs["total"] = val
        return runs, extras, wickets

    # ---------------- NORMAL RUNS ----------------
    if "four" in outcome_l:
        runs["batter"] = 4
    elif "six" in outcome_l:
        runs["batter"] = 6
    else:
        nums = re.findall(r'\d+', outcome)
        if nums:
            runs["batter"] = int(nums[0])

    runs["total"] = runs["batter"]

    return runs, extras, wickets


# ---------------- MAIN ENGINE ----------------

def parse_html(file_path):

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    name_map = build_name_map(soup)

    balls = soup.select("div.border-b")

    overs = {}

    striker, non_striker, current_bowler = extract_initial_players(soup)

    for node in balls:

        text = clean(node.get_text(" ", strip=True))
        raw_html = str(node)

        # ---------------- BOWLER CHANGE ----------------
        if "comes into the attack" in text:
            current_bowler = clean(text.split("(")[0])
            continue

        # ---------------- SKIP NON BALL EVENTS ----------------
        if " to " not in text:
            continue

        # ---------------- OVER EXTRACTION ----------------
        match = re.search(r'(\d+)\.(\d+)', text)
        if not match:
            continue

        over_id = match.group(1)
        ball_id = match.group(2)

        # ---------------- COMMENTARY ----------------
        comm_match = re.search(r'\d+\.\d+\s+(.*)', text)
        if not comm_match:
            continue

        commentary = comm_match.group(1)
        commentary = re.sub(r'\d{1,2}:\d{2}.*', '', commentary)

        parts = commentary.split(",", 1)
        players = clean(parts[0])
        outcome = clean(parts[1]) if len(parts) > 1 else ""

        if " to " not in players:
            continue

        bowler_raw, batter_raw = players.split(" to ")

        bowler = clean(bowler_raw)
        batter_short = clean(re.sub(r'(WIDE|OUT!.*)', '', batter_raw)).strip()
        batter = name_map.get(batter_short, batter_short)

        if current_bowler:
            bowler = current_bowler

        # ---------------- STRIKER SET ----------------
        if striker is None:
            striker = batter
        elif batter != striker:
            non_striker = striker
            striker = batter

        if striker == non_striker:
            non_striker = None

        # ---------------- WICKET DETECTION FIX ----------------
        is_wicket = bool(re.search(r'OUT!|run out|bowled|caught', text, re.IGNORECASE))

        # ---------------- EVENT PARSE ----------------
        runs, extras, wickets = parse_event(outcome, striker, is_wicket)

        delivery = {
            "ball": f"{over_id}.{ball_id}",
            "batter": striker,
            "bowler": bowler,
            "non_striker": non_striker,
            "runs": runs
        }

        if extras:
            delivery["extras"] = extras

        if wickets:
            delivery["wickets"] = wickets

        overs.setdefault(over_id, []).append(delivery)

        # ---------------- STRIKE ROTATION ----------------
        if not extras.get("wides"):
            if runs["batter"] % 2 == 1:
                striker, non_striker = non_striker, striker

        # ---------------- NEW BATSMAN AFTER WICKET ----------------
        if wickets:
            striker = None

    return {
        "innings": [
            {
                "team": "Unknown",
                "overs": [
                    {
                        "over": o,
                        "deliveries": d
                    }
                    for o, d in sorted(overs.items())
                ]
            }
        ]
    }


# ---------------- RUN ----------------

data = parse_html("innings_1_Monument_1st_XI_2026.html")

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("🔥 FULL CRICSHEET ENGINE READY")