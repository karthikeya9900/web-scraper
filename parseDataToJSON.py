from bs4 import BeautifulSoup
from difflib import get_close_matches
import re
import json

# =========================================================
# HELPERS
# =========================================================

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def normalize_team(name):
    if not name:
        return ""

    name = name.lower()
    name = re.sub(r'\b\d{1,2}[:.]\d{2}\s*(am|pm)?\b', '', name)
    name = re.sub(r'\b(am|pm)\b', '', name)
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def normalize_name(name):
    if not name:
        return ""

    name = name.lower()
    name = name.replace("-", " ")
    name = re.sub(r'[^a-z\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def normalize_player_key(name):
    if not name:
        return None

    name = name.lower()
    name = re.sub(r'[^a-z\s]', '', name)
    name = re.sub(r'\s+', '_', name.strip())

    return name


def empty_extras():
    return {
        "wides": 0,
        "byes": 0,
        "legbyes": 0,
        "noballs": 0
    }

# =========================================================
# PLAYER HELPERS
# =========================================================

def extract_players(text):
    # remove ball prefix
    text = re.sub(r'^\d+\.\d+\s*', '', text)

    # ------------------------------------------
    # CLEAN NOISE (IMPORTANT FIX)
    # ------------------------------------------
    text = re.sub(
        r'\b(wd|wides?|nb|no ball|bye|lb)\b\s*\.?\s*',
        ' ',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(r'\b(wides?)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^\w\s\.]', ' ', text)   # remove weird symbols except dot
    text = re.sub(r'\s+', ' ', text).strip()

    # ------------------------------------------
    # NORMAL SPLIT
    # ------------------------------------------
    if " to " not in text:
        return None, None

    try:
        bowler_raw, rest = text.split(" to ", 1)
        batter_raw = re.split(
            r'\b(run|runs|out|lbw|b|c|st|wide|wd|nb|no ball|four|six)\b',
            rest,
            flags=re.IGNORECASE
        )[0]

        bowler = clean_player_name(bowler_raw)
        batter = clean_player_name(batter_raw)

        # ❌ extra safety: reject garbage like "wd"
        if bowler and len(bowler) <= 2:
            bowler = None
        if batter and len(batter) <= 2:
            batter = None

        return bowler, batter
    except:
        return None, None
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

    # remove brackets
    name = re.sub(r'\(.*?\)', '', name)

    # remove comma suffix
    name = name.split(",")[0]

    # remove cricket noise words
    name = re.sub(
        r'\b(PM|AM|WIDE|WIDES|WD|NB|LB|BYE|RUN|RUNS|OUT|FOUR|SIX)\b',
        '',
        name,
        flags=re.IGNORECASE
    )

    # remove prefixes like "wd .", "nb .", etc.
    name = re.sub(r'^(wd|nb|wide|no ball)\s*\.?\s*', '', name, flags=re.IGNORECASE)

    # remove any remaining non-letter prefix
    name = re.sub(r'^[^A-Za-z]+', '', name)   #remove leading junk
    name = re.sub(r'[^A-Za-z\s\.]', '', name)

    # collapse spaces
    name = clean(name)

    return name if name else None

def clean_player_out(name):
    if not name:
        return None

    name = name.lower()

    # remove dismissal words
    name = re.sub(r'\b(lbw|bowled|caught|stumped|c|b|st)\b', '', name)

    # remove run out prefix
    name = re.sub(r'run\s*[- ]?out', '', name)

    # remove "out"
    name = re.sub(r'\bout\b', '', name)

    # cleanup
    name = re.sub(r'\s+', ' ', name).strip()

    return name.title()
def resolve_player(name, registry):
    if not name:
        return None

    norm = normalize_name(name)
    key = normalize_player_key(name)

    if key in registry:
        return registry[key]["full_name"]

    for player in registry.values():
        for alias in player.get("aliases", []):
            if normalize_name(alias) == norm:
                return player["full_name"]

    for player in registry.values():
        full = normalize_name(player["full_name"])
        if norm in full or all(part in full for part in norm.split()):
            return player["full_name"]

    match = get_close_matches(name, [p["full_name"] for p in registry.values()], n=1, cutoff=0.6)
    if match:
        return match[0]

    return name

# =========================================================
# MATCH + TEAM
# =========================================================

def match_team(toss_winner, teams):
    tw = normalize_team(toss_winner)
    tw_words = set(tw.split())

    best_match = None
    best_score = 0

    for team in teams:
        tn = normalize_team(team)
        tn_words = set(tn.split())

        score = len(tw_words & tn_words)

        if score > best_score:
            best_score = score
            best_match = team

    return best_match if best_score > 0 else None


def extract_team_name(soup):
    for btn in soup.select("button.ant-dropdown-trigger"):
        text = clean(btn.get_text(" ", strip=True))
        if text not in ["Old", "All", "", "Members", "Clubs", "Matches", "Statistics", "Series", "League"]:
            return text
    return "Unknown"

# =========================================================
# DISMISSAL
# =========================================================

def extract_dismissal_text(text):
    if "OUT!" in text:
        text = text.split("OUT!", 1)[1]

    # 🔥 remove stats junk
    text = re.sub(r'balls?.*', '', text, flags=re.IGNORECASE)

    # 🔥 remove leading junk
    text = re.sub(r'^[^A-Za-z]+', '', text)

    text = re.sub(r'\s+', ' ', text)
    return clean(text)

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
# INITIAL PLAYERS
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

# =========================================================
# EVENT PARSER
# =========================================================

def parse_event(full_text, batter_name, is_wicket):

    t = full_text.lower()

    runs = {"batter": 0, "extras": 0, "total": 0}
    extras = empty_extras()
    wickets = []

    # =====================================================
    # WICKET HANDLING (FIXED)
    # =====================================================
    if is_wicket:
        dismissal_text = extract_dismissal_text(full_text)
        dt = dismissal_text.lower()

        # -----------------------------------------------------
        # 1. RUN OUT (highest priority)
        # -----------------------------------------------------
        if "run out" in dt:
            m = re.search(
                r'^([A-Za-z\s\.]+)\s+run\s*[- ]?out\s*\(([^)]+)\)',
                dismissal_text,
                re.IGNORECASE
            )

            if m:
                wickets.append({
                    "kind": "run out",
                    "player_out": clean_player_out(m.group(1)),
                    "fielders": [clean(x) for x in m.group(2).split("/")]
                })
            else:
                wickets.append({
                    "kind": "run out",
                    "player_out": batter_name
                })

        # -----------------------------------------------------
        # 2. CAUGHT
        # -----------------------------------------------------
        else:
            m = re.search(
                r'^([A-Za-z\s\.]+?)\s+c\s+([A-Za-z\s\.]+?)\s+b\s+([A-Za-z\s\.]+)',
                dismissal_text
            )

            if m:
                wickets.append({
                    "kind": "caught",
                    "player_out": clean_player_out(m.group(1)),
                    "fielders": [clean(m.group(2))],
                    "bowler": clean(m.group(3))
                })

            # -------------------------------------------------
            # 3. STUMPED
            # -------------------------------------------------
            elif re.search(r'\bst\b', dt):
                m = re.search(
                    r'^([A-Za-z\s\.]+?)\s+st\s+([A-Za-z\s\.]+?)\s+b\s+([A-Za-z\s\.]+)',
                    dismissal_text,
                    re.IGNORECASE
                )

                if m:
                    wickets.append({
                        "kind": "stumped",
                        "player_out": clean_player_out(m.group(1)),
                        "fielders": [clean(m.group(2))],
                        "bowler": clean(m.group(3))
                    })

            # -------------------------------------------------
            # 4. LBW (must come BEFORE bowled)
            # -------------------------------------------------
            elif "lbw" in dt:
                m = re.search(
                    r'([A-Za-z\s\.]+?)\s+lbw\s+b\s+([A-Za-z\s\.]+)',
                    dismissal_text,
                    re.IGNORECASE
                )

                if m:
                    wickets.append({
                        "kind": "lbw",
                        "player_out": clean_player_out(m.group(1)),
                        "bowler": clean(m.group(2))
                    })
                else:
                    wickets.append({
                        "kind": "lbw",
                        "player_out": batter_name
                    })

            # -------------------------------------------------
            # 5. BOWLED (LAST)
            # -------------------------------------------------
            elif re.search(r'\sb\s+', dismissal_text):
                m = re.search(
                    r'^([A-Za-z\s\.]+?)\s+b\s+([A-Za-z\s\.]+)',
                    dismissal_text
                )

                if m:
                    wickets.append({
                        "kind": "bowled",
                        "player_out": clean_player_out(m.group(1)),
                        "bowler": clean(m.group(2))
                    })

            # -------------------------------------------------
            # UNKNOWN
            # -------------------------------------------------
            else:
                wickets.append({
                    "kind": "unknown",
                    "player_out": dismissal_text
                })

        return runs, extras, wickets, True
    # =====================================================
    # RUNS
    # =====================================================
    run_matches = re.findall(r'(\d+)\s*(?:run|runs)', t)
    base_runs = sum(int(n) for n in run_matches) if run_matches else 0

    # =====================================================
    # WIDE (ENHANCED RUN DETECTION — NO NEW KEYS)
    # =====================================================
    if "wide" in t:
        wd_match = re.search(r'\b(\d+)\s*wd\b', t)
        wides = int(wd_match.group(1)) if wd_match else 1
        extras["wides"] = wides
        runs["batter"] = 0
        runs["extras"] = wides
        runs["total"] = wides
        return runs, extras, wickets, False
    if "no ball" in t:
        extras["noballs"] = 1
        if "leg bye" in t:
            extras["legbyes"] = base_runs
            runs["extras"] = 1 + base_runs
        elif "bye" in t:
            extras["byes"] = base_runs
            runs["extras"] = 1 + base_runs
        else:
            runs["batter"] = base_runs
            runs["extras"] = 1
        runs["total"] = runs["batter"] + runs["extras"]
        return runs, extras, wickets, True

    if "leg bye" in t:
        extras["legbyes"] = base_runs or 1
        runs["extras"] = extras["legbyes"]
        runs["total"] = runs["extras"]
        return runs, extras, wickets, True

    if "bye" in t:
        extras["byes"] = base_runs or 1
        runs["extras"] = extras["byes"]
        runs["total"] = runs["extras"]
        return runs, extras, wickets, True

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

    state = {
        "striker": striker,
        "non_striker": non_striker,
        "incoming_batter": None,
        "last_wicket": None,
        "apply_new_batter_next_ball": False,
        "last_ball_was_over_end": False
    }

    overs = {}

    for node in soup.select("div.border-b"):
        text = clean(node.get_text(" ", strip=True))
        text = re.sub(r'^\d+\s+', '', text)

        # ------------------------------------------
        # NEW BATTER ENTRY
        # ------------------------------------------
        if "comes to the crease" in text:
            new_player = clean_player_name(text.split("comes")[0])
            resolved = resolve_player(new_player, registry)

            if resolved:
                state["incoming_batter"] = resolved
            continue

        # ------------------------------------------
        # DELIVERY DETECTION
        # ------------------------------------------
        match = re.search(r'(\d+)\.(\d+)', text)
        if not match:
            continue

        over_id, ball_id = match.groups()

        # ------------------------------------------
        # APPLY NEW BATTER
        # ------------------------------------------
        if state["apply_new_batter_next_ball"] and state["incoming_batter"]:

            if state["last_wicket"]:
                was_striker = state["last_wicket"]["was_striker"]

                if was_striker:
                    if state["last_ball_was_over_end"]:
                        state["non_striker"] = state["incoming_batter"]
                    else:
                        state["striker"] = state["incoming_batter"]
                else:
                    state["non_striker"] = state["incoming_batter"]

            state["incoming_batter"] = None
            state["last_wicket"] = None
            state["apply_new_batter_next_ball"] = False

        # ------------------------------------------
        # EXTRACT PLAYERS
        # ------------------------------------------
        bowler, batter = extract_players(text)
        if not bowler or not batter:
            continue

        bowler = resolve_player(bowler, registry)
        parsed_batter = resolve_player(batter, registry)
        # ✅ FORCE STRIKER SYNC WITH UI
        if parsed_batter and state["striker"] != parsed_batter:
            if parsed_batter == state["non_striker"]:
                state["striker"], state["non_striker"] = state["non_striker"], state["striker"]
            else:
                state["striker"] = parsed_batter

                if state["striker"] is None:
                    state["striker"] = parsed_batter

        is_wicket = "OUT!" in text

        runs, extras, wickets, is_legal = parse_event(
            text, state["striker"], is_wicket
        )

        # ------------------------------------------
        # WICKET HANDLING
        # ------------------------------------------
        if wickets:
            out_player = resolve_player(wickets[0]["player_out"], registry)

            state["last_wicket"] = {
                "player_out": out_player,
                "was_striker": (state["striker"] == out_player)
            }

            state["apply_new_batter_next_ball"] = True

        # ------------------------------------------
        # SAFE FALLBACK (FIXED)
        # ------------------------------------------
        if state["non_striker"] is None:
            if parsed_batter != state["striker"]:
                state["non_striker"] = parsed_batter
            # ❌ DO NOT assign "Unknown"

        # ------------------------------------------
        # CREATE DELIVERY
        # ------------------------------------------
        delivery = {
            "ball": f"{over_id}.{ball_id}",
            "batter": state["striker"],
            "bowler": bowler,
            "non_striker": state["non_striker"],
            "runs": runs
        }

        if any(extras.values()):
            delivery["extras"] = extras

        if wickets:
            delivery["wickets"] = wickets

        overs.setdefault(over_id, []).append(delivery)

        # ------------------------------------------
        # STRIKE ROTATION (FINAL CORRECT LOGIC ✅)
        # ------------------------------------------

        if is_legal:
            # rotate on batter runs only
            if not wickets and runs.get("batter", 0) % 2 == 1:
                state["striker"], state["non_striker"] = state["non_striker"], state["striker"]

            # over-end rotation
            if ball_id == "6":
                state["striker"], state["non_striker"] = state["non_striker"], state["striker"]
                state["last_ball_was_over_end"] = True
            else:
                state["last_ball_was_over_end"] = False
        else:
            state["last_ball_was_over_end"] = False
    return {
        "team": team_name,
        "overs": [
            {"over": o, "deliveries": d}
            for o, d in sorted(overs.items(), key=lambda x: int(x[0]))
        ]
    }

# =========================================================
# MAIN API
# =========================================================

def sanitize_registry(registry):
    return {
        key: {
            "full_name": value["full_name"],
            "aliases": list(value["aliases"])
        }
        for key, value in registry.items()
    }


def extract_match_meta(soup):
    title = clean(soup.title.string) if soup.title else ""
    parts = title.split(" - ")

    return {
        "match": parts[0] if len(parts) > 0 else "",
        "league": parts[1] if len(parts) > 1 else ""
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

            return {
                "winner": winner,
                "decision": "field" if decision == "bowl" else decision
            }

    return None


def order_innings(innings_list, toss_info):
    if not toss_info or len(innings_list) < 2:
        return innings_list

    teams = [inn["team"] for inn in innings_list]
    matched_team = match_team(toss_info["winner"], teams)

    if not matched_team:
        return innings_list

    opponent = [t for t in teams if t != matched_team]
    if not opponent:
        return innings_list

    opponent = opponent[0]

    first_team = matched_team if toss_info["decision"] == "bat" else opponent

    return sorted(innings_list, key=lambda x: 0 if x["team"] == first_team else 1)


def generate_match_json(files, output_file=None):
    match_context = {
        "meta": {},
        "toss": None,
        "teams": set(),
        "player_registry": {},
        "innings_raw": []
    }

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        if not match_context["meta"]:
            match_context["meta"] = extract_match_meta(soup)

        if not match_context["player_registry"]:
            match_context["player_registry"] = extract_player_registry(soup)

        if match_context["toss"] is None:
            match_context["toss"] = extract_toss_info(soup)

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


if __name__ == "__main__":
    files = ["innings_1.html", "innings_2.html"]
    generate_match_json(files, "output.json")
    print("✅ JSON generated")