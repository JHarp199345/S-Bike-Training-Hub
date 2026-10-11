import sys, pathlib, tempfile; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import paths

code = pathlib.Path(tempfile.mkdtemp())
assert paths.resolve(code, {}) == code                                   # fresh checkout: as before
(code / ".packaged").write_text("")
assert paths.resolve(code, {}) == paths.user_folder()                    # packaged: the user's data folder
(code / "coach.json").write_text("{}")
assert paths.resolve(code, {}) == code                                   # data already here: never moved
custom = pathlib.Path(tempfile.mkdtemp()) / "mine"
assert paths.resolve(code, {"S_BIKE_HUB_DATA": str(custom)}) == custom.resolve()   # explicit choice wins
(code / "workouts").mkdir(); (code / "workouts" / "1-erg-check.json").write_text("{}")
d = paths.seed(custom, code)
assert d == custom and (custom / "workouts" / "1-erg-check.json").exists()          # a new folder gets the samples
(custom / "workouts" / "mine.json").write_text("{}"); paths.seed(custom, code)
assert (custom / "workouts" / "mine.json").exists()                     # and they're never replaced later
print("PASS paths: data folder choice and first-run seeding")
