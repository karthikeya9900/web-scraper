import json
import csv
import re

INPUT_FILE = "output.json"
OUTPUT_FILE = "cricbuzz_merged.csv"


def clean_bowler(name):
    if not name:
        return ""
    return re.sub(r'^(wd|lb|W)\s*\.\s*', '', name).strip()


def is_illegal_delivery(extras):
    if not extras:
        return False
    return extras.get("wides", 0) > 0 or extras.get("noballs", 0) > 0


def convert():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    match_id = data["meta"]["match"]

    for innings_idx, innings in enumerate(data["innings"], start=1):
        batting_team = innings["team"]
        bowling_team = [t for t in data["teams"] if t != batting_team][0]

        for over_data in innings["overs"]:
            over = int(over_data["over"])

            ball_count = 0
            current_ball = None
            agg = None

            for d in over_data["deliveries"]:
                ball_id = d["ball"]

                runs = d.get("runs", {})
                extras = d.get("extras", {})
                wickets = d.get("wickets", [])

                # Start new ball aggregation
                if current_ball != ball_id:
                    # flush previous
                    if agg:
                        rows.append(agg)

                    current_ball = ball_id
                    agg = {
                        "match_id": match_id,
                        "innings": innings_idx,
                        "batting_team": batting_team,
                        "bowling_team": bowling_team,
                        "over": over,
                        "ball_raw": ball_id,

                        "batter": d.get("batter"),
                        "bowler": clean_bowler(d.get("bowler")),
                        "non_striker": d.get("non_striker"),

                        "runs_off_bat": 0,
                        "extras": 0,
                        "total_runs": 0,

                        "wides": 0,
                        "noballs": 0,
                        "byes": 0,
                        "legbyes": 0,

                        "is_wicket": 0,
                        "wicket_type": "",
                        "player_out": "",
                        "fielders": ""
                    }

                # accumulate runs
                agg["runs_off_bat"] += runs.get("batter", 0)
                agg["extras"] += runs.get("extras", 0)
                agg["total_runs"] += runs.get("total", 0)

                # accumulate extras
                agg["wides"] += extras.get("wides", 0)
                agg["noballs"] += extras.get("noballs", 0)
                agg["byes"] += extras.get("byes", 0)
                agg["legbyes"] += extras.get("legbyes", 0)

                # wicket
                if wickets:
                    w = wickets[0]
                    agg["is_wicket"] = 1
                    agg["wicket_type"] = w.get("kind", "")
                    agg["player_out"] = w.get("player_out", "")
                    agg["fielders"] = ", ".join(w.get("fielders", []))

                # legal ball detection
                if not is_illegal_delivery(extras):
                    ball_count += 1
                    agg["over_ball"] = f"{over}.{ball_count}"

            # flush last ball
            if agg:
                rows.append(agg)

    # Write CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("✅ Merged Cricbuzz CSV created!")


if __name__ == "__main__":
    convert()