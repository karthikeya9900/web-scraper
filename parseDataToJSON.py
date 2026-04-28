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

def extract_initial_players(soup):
    batsmen = []
    bowler = None

    blocks = soup.select("div.border-b")

    for block in blocks:
        text = clean(block.get_text(" ", strip=True))

        # ✅ get batsmen BEFORE ball-by-ball
        if "comes to the crease" in text:
            name = clean_player_name(text.split("comes")[0])

            if name and name not in batsmen:
                batsmen.append(name)

        # ✅ get first bowler
        if "comes into the attack" in text and bowler is None:
            bowler = clean_player_name(text.split("(")[0])

        if len(batsmen) >= 2 and bowler:
            break

    striker = batsmen[0] if len(batsmen) > 0 else None
    non_striker = batsmen[1] if len(batsmen) > 1 else None

    return striker, non_striker, bowler


def clean_player_name(name):
    if not name:
        return None

    name = re.sub(r'\(.*?\)', '', name)   # remove (93)
    name = name.split(",")[0]             # remove after comma
    name = re.sub(r'\b(PM|AM|WIDE|NB|LB|BYE|OUT|FOUR|SIX)\b.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^A-Za-z\s]', '', name)

    return clean(name)


# ---------------- PLAYER EXTRACTION ----------------

def extract_players(text):
    m = re.search(r'\d+\.\d+\s+(.*)', text)
    if not m:
        return None, None

    line = m.group(1)

    # ✅ FIX: remove commentary BEFORE splitting
    line = line.split(",")[0]

    if " to " not in line:
        return None, None

    bowler_raw, batter_raw = line.split(" to ")

    bowler = clean_player_name(bowler_raw)
    batter = clean_player_name(batter_raw)

    return bowler, batter


# ---------------- EVENT PARSER (UNCHANGED) ----------------

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


# ---------------- MAIN ENGINE ----------------

def parse_html(file_path):

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    balls = soup.select("div.border-b")

    overs = {}

    striker, non_striker, current_bowler = extract_initial_players(soup)

    for node in balls:

        text = clean(node.get_text(" ", strip=True))

        # bowler change
        if "comes into the attack" in text:
            current_bowler = clean_player_name(text.split("(")[0])
            continue

        match = re.search(r'(\d+)\.(\d+)', text)
        if not match:
            continue

        over_id, ball_id = match.groups()

        bowler, batter = extract_players(text)

        if not bowler or not batter:
            continue

        # ✅ FIX: PROPER INITIALIZATION (no continue!)
        if striker is None:
            striker = batter

        elif non_striker is None:
            if batter != striker:
                non_striker = batter

        # ❌ DO NOT clean None repeatedly (safe)
        striker = clean_player_name(striker) if striker else striker
        non_striker = clean_player_name(non_striker) if non_striker else non_striker
        bowler = clean_player_name(bowler)

        is_wicket = "OUT!" in text

        runs, extras, wickets, legal_delivery = parse_event(text, striker, is_wicket)

        delivery = {
            "ball": f"{over_id}.{ball_id}",
            "batter": striker,
            "bowler": bowler,
            "non_striker": non_striker,
            "runs": runs
        }

        if any(v > 0 for v in extras.values()):
            delivery["extras"] = extras

        if wickets:
            delivery["wickets"] = wickets

        overs.setdefault(over_id, []).append(delivery)

        # strike rotation
        if legal_delivery and runs["batter"] % 2 == 1:
            striker, non_striker = non_striker, striker

        # wicket
        if wickets:
            striker = None

    return {
        "innings": [
            {
                "team": "Unknown",
                "overs": [
                    {"over": o, "deliveries": d}
                    for o, d in sorted(overs.items(), key=lambda x: int(x[0]))
                ]
            }
        ]
    }


# ---------------- RUN ----------------

data = parse_html("innings_1.html")

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("✅ FIXED WITHOUT BREAKING YOUR LOGIC")