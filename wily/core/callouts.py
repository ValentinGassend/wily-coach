"""The names players and pros call (FACEIT, pro teams), instead of the game's own place names.

The demos only give CS2's place names (nav areas: "ExtendedA", "UpperTunnel", "SnipersNest"...). This table turns
them into the callouts used in pro and FACEIT comms ("Short", "Upper Tunnels", "Window"...). A name is only changed
when the callout clearly covers the same area; otherwise the game's name stays (spaced out).
Sources: community callout maps (Total CS, https://totalcsgo.com/callouts; Ultimate Move,
https://ultimatemove.eu/en/cs2-callouts/), checked against where the Ts and CTs of the base actually stand in each area.
"""

GENERIC = {
    "BombsiteA": "A Site", "BombsiteB": "B Site", "CTSpawn": "CT Spawn", "TSpawn": "T Spawn", "ctspawn": "CT Spawn", "tspawn": "T Spawn",
    "Middle": "Mid", "TopofMid": "Top Mid", "SecondMid": "Second Mid", "LowerMid": "Lower Mid",
    "PalaceInterior": "Palace", "Apartments": "Apps", "SnipersNest": "Sniper's Nest", "Restroom": "Toilets",
}

MAPS = {
    # 22/10, his test video: "Outside Tunnel, personne ne le sait": the tunnels' way in from T Spawn is "Tunnels"
    "de_dust2": {
        "LongA": "Long", "OutsideLong": "Outside Long", "LongDoors": "Long Doors", "Side": "Side Pit", "ARamp": "A Ramp",
        "ExtendedA": "Short", "ShortStairs": "Short Stairs", "Catwalk": "Catwalk", "UnderA": "Under A",
        "MidDoors": "Mid Doors", "UpperTunnel": "Upper Tunnels", "LowerTunnel": "Lower Tunnels", "OutsideTunnel": "Tunnels",
        "TunnelStairs": "Tunnel Stairs", "BDoors": "B Doors", "Hole": "B Window", "TRamp": "T Ramp",
    },
    "de_mirage": {
        "TRamp": "A Ramp", "PalaceAlley": "Palace Alley", "SnipersNest": "Window", "Ladder": "Ladder Room", "Catwalk": "Short",
        "Truck": "Van", "Shop": "Market", "BackAlley": "Back Alley", "SideAlley": "Side Alley",
    },
    "de_inferno": {
        "BackAlley": "Alley", "TRamp": "T Ramp",
    },
    "de_ancient": {
        "MainHall": "A Main", "SideHall": "Donut", "SideEntrance": "Cave", "Ramp": "B Ramp", "TSideLower": "T Lower", "TSideUpper": "T Upper",
    },
    "de_anubis": {
        "Main": "A Main", "OutsideLong": "B Main", "Canal": "Canals", "TSideUpper": "T Upper", "CTSideUpper": "CT Upper",
    },
    "de_vertigo": {
        "TCorridorUp": "T Corridor", "LadderBottom": "Ladder Bottom", "LadderTop": "Ladder Top", "APlatform": "A Platform", "BPlatform": "B Platform",
    },
    "de_train": {
        "LongDog": "Popdog", "TSideUpper": "T Upper",
    },
    "de_nuke": {
        "LockerRoom": "Lockers",
    },
    "de_cache": {
        "ForkLift": "Forklift",
    },
}


def name(place, mp=None):
    """The callout of a place on a map, or None when the game's own name should be used."""
    if not isinstance(place, str):
        return None
    return (MAPS.get(mp) or {}).get(place) or GENERIC.get(place)
