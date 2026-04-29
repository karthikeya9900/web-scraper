from bs4 import BeautifulSoup
import json
import re

# =========================================================
# HELPERS
# =========================================================

def match_team(toss_winner, teams):
    tw = normalize_team(toss_winner)
    tw_words = set(tw.split())

    best_match = None
    best_score = 0

    for team in teams:
        tn = normalize_team(team)
        tn_words = set(tn.split())

        # overlap score
        score = len(tw_words & tn_words)

        if score > best_score:
            best_score = score
            best_match = team

    return best_match if best_score > 0 else None


def normalize_team(name):
    if not name:
        return ""

    name = name.lower()

    # remove time patterns like 10:30 AM
    name = re.sub(r'\b\d{1,2}[:.]\d{2}\s*(am|pm)?\b', '', name)

    # remove standalone AM/PM
    name = re.sub(r'\b(am|pm)\b', '', name)

    # remove special chars but KEEP numbers
    name = re.sub(r'[^a-z0-9\s]', '', name)

    # normalize spaces
    name = re.sub(r'\s+', ' ', name).strip()

    return name


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

def parse_dismissal(full_text, batter_name):

    text = full_text

    # remove score tail (after runs)
    text = re.split(r'\d+\s*\(', text)[0]

    # normalize
    text = clean(text)

    # ---------------- CAUGHT ----------------
    m = re.search(r'^([A-Za-z\s\.]+?)\s+c\s+([A-Za-z\s\.]+?)\s+b\s+([A-Za-z\s\.]+)', text)
    if m:
        return {
            "kind": "caught",
            "player_out": clean(m.group(1)),
            "fielders": [clean(m.group(2))],
            "bowler": clean(m.group(3))
        }

    # ---------------- STUMPED ----------------
    m = re.search(r'^([A-Za-z\s\.]+?)\s+st\s+([A-Za-z\s\.]+?)\s+b\s+([A-Za-z\s\.]+)', text, re.IGNORECASE)
    if m:
        return {
            "kind": "stumped",
            "player_out": clean(m.group(1)),
            "fielders": [clean(m.group(2))],
            "bowler": clean(m.group(3))
        }

    # ---------------- RUN OUT ----------------
    m = re.search(r'^([A-Za-z\s\.]+?)\s+run out\s*\(([^)]+)\)', text, re.IGNORECASE)
    if m:
        fielders = [clean(x) for x in m.group(2).split("/")]
        return {
            "kind": "run out",
            "player_out": clean(m.group(1)),
            "fielders": fielders
        }

    # ---------------- LBW ----------------
    m = re.search(r'^([A-Za-z\s\.]+?)\s+lbw\s+b\s+([A-Za-z\s\.]+)', text, re.IGNORECASE)
    if m:
        return {
            "kind": "lbw",
            "player_out": clean(m.group(1)),
            "bowler": clean(m.group(2))
        }

    # ---------------- BOWLED ----------------
    m = re.search(r'^([A-Za-z\s\.]+?)\s+b\s+([A-Za-z\s\.]+)', text)
    if m:
        return {
            "kind": "bowled",
            "player_out": clean(m.group(1)),
            "bowler": clean(m.group(2))
        }

    # ---------------- FALLBACK ----------------
    return {
        "kind": "unknown",
        "player_out": batter_name
    }


def detect_wicket_type(text):
    t = text.lower()

    if "bowled" in t:
        return "bowled"
    if "caught" in t or "catch" in t:   # ✅ FIXED_BUG
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

    decision = toss_info["decision"]
    teams = [inn["team"] for inn in innings_list]

    matched_team = match_team(toss_info["winner"], teams)

    if not matched_team:
        print("❌ Could not match toss winner:", toss_info["winner"])
        return innings_list

    opponent = [t for t in teams if t != matched_team][0]

    first_team = matched_team if decision == "bat" else opponent

    return sorted(
        innings_list,
        key=lambda x: 0 if x["team"] == first_team else 1
    )


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

    # ---------------- COMMENTARY ONLY ----------------
    parts = full_text.split(",", 1)
    t = parts[1].lower() if len(parts) > 1 else full_text.lower()

    runs = {"batter": 0, "extras": 0, "total": 0}
    extras = empty_extras()
    wickets = []

    # ---------------- WICKET ----------------
    if is_wicket:
        kind = detect_wicket_type(t)

        out_match = re.search(r'^([A-Za-z\s\.]+?)\s+(c|b|lbw|run out|st)', full_text)
        player_out = clean(out_match.group(1)) if out_match else batter_name

        wickets.append({
            "kind": kind,
            "player_out": player_out,
            "fielders": extract_fielders(full_text)
        })

        if kind != "run out":
            return runs, extras, wickets, True

    # ---------------- RUN EXTRACTION ----------------
    run_matches = re.findall(r'(\d+)\s*(?:run|runs)', t)
    run_values = [int(n) for n in run_matches]

    if run_values:
        base_runs = sum(run_values)
    else:
        fallback = re.findall(r'\b\d+\b', t)
        base_runs = int(fallback[0]) if fallback else 0

    # ---------------- WIDE ----------------
    if "wide" in t:
        run_matches = re.findall(r'(\d+)\s*wides?', t)

        if run_matches:
            total = int(run_matches[0])
        else:
            total = 1  # default ICC rule

        extras["wides"] = total
        runs["extras"] = total
        runs["total"] = total

        return runs, extras, wickets, False

    # ---------------- NO BALL ----------------
    if "no ball" in t:
        extras["noballs"] = 1

        if "leg bye" in t:
            extras["legbyes"] = base_runs
            runs["extras"] = 1 + base_runs

        elif re.search(r'\bbye\b', t):
            extras["byes"] = base_runs
            runs["extras"] = 1 + base_runs

        else:
            runs["batter"] = base_runs
            runs["extras"] = 1

        runs["total"] = runs["batter"] + runs["extras"]
        return runs, extras, wickets, True

    # ---------------- LEG BYE ----------------
    if "leg bye" in t:
        extras["legbyes"] = base_runs if base_runs else 1

        runs["batter"] = 0
        runs["extras"] = extras["legbyes"]
        runs["total"] = runs["extras"]

        return runs, extras, wickets, True

    # ---------------- BYE ----------------
    if re.search(r'\bbye\b', t):
        extras["byes"] = base_runs if base_runs else 1

        runs["batter"] = 0
        runs["extras"] = extras["byes"]
        runs["total"] = runs["extras"]

        return runs, extras, wickets, True

    # ---------------- NORMAL RUNS ----------------
    runs["batter"] = base_runs
    runs["total"] = base_runs

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

        runs, extras, wickets, is_legal = parse_event(
            text, batter, "OUT!" in text
        )

        # =====================================================
        # 🔥 1. REMOVE OUT PLAYER FIRST
        # =====================================================
        if wickets:
            out_player = wickets[0]["player_out"]

            if out_player == striker:
                striker = None
            elif out_player == non_striker:
                non_striker = None

        # =====================================================
        # 🔥 2. ASSIGN STRIKER PROPERLY
        # =====================================================
        if striker is None:
            striker = batter

        current_striker = batter

        # =====================================================
        # 🔥 3. PREVENT SAME PLAYER BOTH SIDES
        # =====================================================
        if non_striker == current_striker:
            non_striker = None

        # =====================================================
        # 🔥 4. BUILD DELIVERY (CLEAN STATE)
        # =====================================================
        delivery = {
            "ball": f"{over_id}.{ball_id}",
            "batter": current_striker,
            "bowler": bowler,
            "non_striker": non_striker,
            "runs": runs
        }

        if any(extras.values()):
            delivery["extras"] = extras

        if wickets:
            delivery["wickets"] = wickets

        overs.setdefault(over_id, []).append(delivery)

        # =====================================================
        # 🔥 5. STRIKE ROTATION
        # =====================================================
        if is_legal:
            if runs["total"] % 2 == 1:
                striker, non_striker = non_striker, current_striker
            else:
                striker = current_striker

            # over end rotation
            if ball_id == "6":
                striker, non_striker = non_striker, striker

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