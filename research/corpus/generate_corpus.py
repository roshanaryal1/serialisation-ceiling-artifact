#!/usr/bin/env python3
"""Synthetic equipment-listing corpus generator for the browser-native
retrieval benchmark (RESEARCH_PLAN.md Phase 2).

Design, per the plan:
  - Templated combinatorial generation over a controlled vocabulary, not LLM
    generation, so it's reproducible from a seed, costs nothing, and doesn't
    import a second model's biases into the corpus (RESEARCH_PLAN.md Phase 2).
  - Field-length and price distributions are anchored to the 48-item
    developer fixture in src/components/admin/PopulateFirebase.js, documented
    in research/corpus/DISTRIBUTIONS.md. This is fixture data, not production
    listings (RentMate is pre-launch) -- stated in DISTRIBUTIONS.md and must
    be repeated in the paper's limitations section, not softened.
  - Corpus sizes are STRICT SUPERSETS of each other: one seeded stream is
    generated once, in a fixed order, and corpus_Nk is simply the first N*1000
    records of that stream. Scaling curves are therefore never confounded by
    content differences between corpus sizes.

Category coverage: 23 of the 31 enum categories (AddEquipment.js:54-87) have
>=1 example in the fixture; 8 have zero. For the 8 empty categories, vocab
below is authored (not mined) by analogy to the closest populated category
-- flagged explicitly in CATEGORIES below with EXTRAPOLATED=True. This is a
design decision, not an empirical fact, and must be stated as such if cited.

Usage:
    python3 generate_corpus.py --sizes 1000 10000 100000 --seed 42
    python3 generate_corpus.py --sizes 250000 500000 --seed 42   # reserve arms
"""

import argparse
import json
import re
from pathlib import Path

SEED_DEFAULT = 42
OUTPUT_DIR = Path(__file__).parent

# ─── Vocabulary ────────────────────────────────────────────────────────────
# Each category: types (base equipment nouns), modifiers (spec/size variants),
# purpose_templates ({type} placeholder, mirrors the fixture's one-sentence
# purpose-statement style -- see DISTRIBUTIONS.md: median 7 words / 49 chars),
# features (pool to draw exactly 3 from, per DISTRIBUTIONS.md: constant count
# = 3 in the fixture), price_range (NZD/day; from the per-category min/max in
# the 48-item fixture where n>=2, else the fixture's global min/max as a
# fallback for n<2 and EXTRAPOLATED categories).

CATEGORIES = {
    "Construction Equipment": dict(extrapolated=False, price_range=(280, 1500),
        types=["Excavator", "Bulldozer", "Backhoe Loader", "Wheel Loader", "Pile Driver", "Skid Steer Loader"],
        modifiers=["Compact", "Heavy-Duty", "20-ton", "35-ton", "70-ton", "Mini", "Standard", "Long-Reach"],
        purpose_templates=["Ideal for {t} work on active construction sites.", "Used for heavy material handling and site clearing with a {t}.", "Versatile {t} for small to large construction jobs."],
        features=["High-reach arm", "Advanced hydraulics", "Reinforced tracks", "ROPS certified", "4WD capability", "Pilot controls", "Side shift", "Fuel efficient engine"]),
    "Material Handling": dict(extrapolated=False, price_range=(180, 350),
        types=["Forklift", "Telehandler", "Pallet Jack", "Order Picker"],
        modifiers=["Electric", "2,500 lb capacity", "5,000 lb capacity", "All-Terrain", "Narrow Aisle"],
        purpose_templates=["Used for lifting and transporting materials with a {t}.", "Warehouse-ready {t} for daily loading tasks.", "All-terrain {t} for varied site heights."],
        features=["Electric operation", "Side shift", "Full free lift mast", "42ft lift height", "All terrain tires", "Level 1 stabilizers"]),
    "Aerial Equipment": dict(extrapolated=False, price_range=(220, 550),
        types=["Scissor Lift", "Boom Lift", "Cherry Picker"],
        modifiers=["19' Electric", "26' Electric", "32' Electric", "40' Articulating", "45' Articulating", "60' Telescopic"],
        purpose_templates=["Elevates workers safely for indoor and outdoor tasks with a {t}.", "Provides flexible reach for elevated work using a {t}.", "Extended-reach {t} for complex maintenance projects."],
        features=["Electric drive", "Non-marking tires", "Platform extension", "Self-leveling jacks", "Pothole guards", "Articulating boom", "360° turntable"]),
    "Concrete Equipment": dict(extrapolated=False, price_range=(150, 850),
        types=["Concrete Mixer", "Concrete Pump", "Concrete Vibrator", "Power Trowel"],
        modifiers=["1.5 cu yd", "Trailer-Mounted", "Diesel", "Walk-Behind", "Self-Loading"],
        purpose_templates=["Mixes and places concrete on-site with a {t}.", "Pumps concrete to hard-to-reach areas using a {t}.", "Finishes concrete surfaces efficiently with a {t}."],
        features=["Diesel powered", "Self-loading", "Hydraulic transmission", "Boom reach 32m", "Remote control", "Auto wash system"]),
    "Landscaping": dict(extrapolated=False, price_range=(95, 450),
        types=["Stump Grinder", "Wood Chipper", "Lawn Mower", "Hedge Trimmer"],
        modifiers=["6-inch", "Ride-On", "Walk-Behind", "Gas-Powered", "Remote Control"],
        purpose_templates=["Clears land and green waste with a {t}.", "Maintains large lawns and grounds using a {t}.", "Shreds branches and debris efficiently with a {t}."],
        features=["Rubber tracks", "Remote control", "Cutter wheel protection", "Self-feeding", "Zero turn radius", "Mulching deck"]),
    "Transportation": dict(extrapolated=False, price_range=(380, 950),
        types=["Dump Truck", "Articulated Dump Truck", "Flatbed Trailer", "Tipper Truck"],
        modifiers=["10-cube", "40-ton", "45-ton", "6x6", "Heavy-Duty"],
        purpose_templates=["Transports loose materials with a {t}.", "Heavy-duty hauler for rough terrain, a {t}.", "Moves equipment and materials between sites with a {t}."],
        features=["Auto tarp system", "Weight distribution", "GPS tracking", "6x6 drive", "Automatic transmission", "Traction control"]),
    "Pumps": dict(extrapolated=False, price_range=(85, 300),
        types=["Water Pump", "Trash Pump", "Submersible Pump"],
        modifiers=["2-inch", "3-inch", "Self-Priming", "Diesel", "Electric"],
        purpose_templates=["Removes water from flooded or excavated areas with a {t}.", "Drains construction sites efficiently using a {t}.", "Moves high volumes of water with a {t}."],
        features=["Self-priming", "Trash pump design", "Honda engine", "Weather protection", "Auto start"]),
    "Excavation": dict(extrapolated=False, price_range=(185, 450),
        types=["Trencher", "Post Hole Digger", "Auger"],
        modifiers=["Walk-Behind", "Ride-On", "Hydraulic", "PTO-Driven"],
        purpose_templates=["Digs trenches for utilities or irrigation with a {t}.", "Digs holes for fencing or signage using a {t}.", "Deep-digging {t} for foundation and drainage work."],
        features=["Variable depth", "Edging blade", "Ground drive", "PTO driven", "Various auger sizes", "Heavy duty gearbox"]),
    "Compaction": dict(extrapolated=False, price_range=(120, 650),
        types=["Plate Compactor", "Roller Compactor", "Road Roller"],
        modifiers=["Single Drum", "Double Drum", "Vibratory", "Walk-Behind"],
        purpose_templates=["Compacts soil or asphalt for stable surfaces with a {t}.", "Smooths and compacts large areas using a {t}.", "Prepares road surfaces for paving with a {t}."],
        features=["Water tank", "Anti-vibration handle", "Honda engine", "Vibratory drum", "Articulated frame", "ROPS cabin"]),
    "Cutting Tools": dict(extrapolated=False, price_range=(65, 180),
        types=["Concrete Saw", "Chain Saw", "Tile Cutter"],
        modifiers=["Walk-Behind", "Gas-Powered", "14-inch blade", "Wet Saw"],
        purpose_templates=["Cuts concrete or masonry with a {t}.", "Cuts trees and large branches with a {t}.", "Precision-cuts tile and stone using a {t}."],
        features=["Wet cutting", "14-inch blade", "Electric start", "Anti-vibration", "Quick tensioning", "Laser guide"]),
    "Air Tools": dict(extrapolated=False, price_range=(150, 300),
        types=["Air Compressor", "Pneumatic Nailer", "Air Ratchet"],
        modifiers=["Portable", "185 CFM", "Diesel", "Electric"],
        purpose_templates=["Powers pneumatic tools on-site with a {t}.", "Supplies compressed air for job-site tools using a {t}.", "Drives fastening and cutting tools with a {t}."],
        features=["Diesel powered", "Aftercooler", "Oil separator", "Portable frame", "Low noise operation"]),
    "Power Generation": dict(extrapolated=False, price_range=(120, 220),
        types=["Generator", "Portable Power Station"],
        modifiers=["10 kW", "20 kW", "Diesel", "Silent"],
        purpose_templates=["Provides temporary power for tools and lighting with a {t}.", "Backs up site power for construction crews using a {t}.", "Supplies higher-capacity power for larger sites with a {t}."],
        features=["Auto start", "Weather protection", "Low noise operation", "Digital controller", "Block heater", "Sound attenuated"]),
    "Cranes": dict(extrapolated=False, price_range=(1800, 2500),
        types=["Mobile Crane", "Tower Crane"],
        modifiers=["30-ton", "50-ton", "Self-Erecting", "Hydraulic Boom"],
        purpose_templates=["Lifts heavy materials to height with a {t}.", "Serves high-rise building projects using a {t}.", "Provides stationary heavy lifting with a {t}."],
        features=["Hydraulic boom", "Outriggers", "Load block", "Self-erecting", "Cabin lift", "Anti-collision system"]),
    "Demolition Tools": dict(extrapolated=False, price_range=(85, 300),
        types=["Jackhammer", "Demolition Hammer", "Breaker"],
        modifiers=["Electric", "Hydraulic", "Pneumatic"],
        purpose_templates=["Breaks up concrete or asphalt with a {t}.", "Demolishes masonry structures using a {t}.", "Precision demolition work with a {t}."],
        features=["Anti-vibration", "Variable speed", "Quick change chuck", "Enclosed hammer", "Variable energy"]),
    "Safety Equipment": dict(extrapolated=False, price_range=(35, 150),
        types=["Scaffolding System", "Safety Barrier", "Harness Kit"],
        modifiers=["Modular", "Quick-Assembly", "Heavy-Duty"],
        purpose_templates=["Provides safe platforms for workers at height with a {t}.", "Secures work zones on-site using a {t}.", "Protects workers during elevated tasks with a {t}."],
        features=["Quick assembly", "Guard rails", "Non-slip planks", "Weather resistant"]),
    "Welding Equipment": dict(extrapolated=False, price_range=(95, 300),
        types=["Welding Machine", "Plasma Cutter"],
        modifiers=["MIG, 200A", "TIG", "Portable", "Digital"],
        purpose_templates=["Joins metal pieces for structural work with a {t}.", "Cuts and shapes metal on-site using a {t}.", "Fabricates and repairs steel components with a {t}."],
        features=["Digital display", "Wire feed motor", "Thermal overload", "Portable frame"]),
    "Cleaning Equipment": dict(extrapolated=False, price_range=(75, 250),
        types=["Pressure Washer", "Industrial Vacuum", "Floor Scrubber"],
        modifiers=["3000 PSI", "Hot Water", "Portable"],
        purpose_templates=["Cleans equipment, surfaces, or buildings with a {t}.", "Removes debris and dirt from job sites using a {t}.", "Prepares surfaces for finishing with a {t}."],
        features=["Hot water option", "Adjustable pressure", "Chemical injection"]),
    "Surface Preparation": dict(extrapolated=False, price_range=(120, 300),
        types=["Sandblaster", "Floor Grinder", "Shot Blaster"],
        modifiers=["Portable", "Walk-Behind", "Dustless"],
        purpose_templates=["Cleans or preps surfaces with abrasive media using a {t}.", "Prepares concrete floors for coating with a {t}.", "Strips old finishes from surfaces with a {t}."],
        features=["Moisture trap", "Adjustable flow", "Large capacity hopper"]),
    "Painting Equipment": dict(extrapolated=False, price_range=(95, 300),
        types=["Paint Sprayer", "Airless Sprayer", "Texture Sprayer"],
        modifiers=["Airless", "HVLP", "Portable"],
        purpose_templates=["Applies paint quickly over large areas with a {t}.", "Coats surfaces evenly using a {t}.", "Finishes interior and exterior paint jobs with a {t}."],
        features=["Variable pressure", "Reversible tip", "Hose length 15m"]),
    "Plumbing Tools": dict(extrapolated=False, price_range=(85, 300),
        types=["Pipe Threader", "Drain Snake", "Pipe Bender"],
        modifiers=["Electric", "Manual", "Multiple pipe sizes"],
        purpose_templates=["Cuts and threads pipes for plumbing installations with a {t}.", "Clears blocked drains and pipes using a {t}.", "Shapes pipe runs for plumbing work with a {t}."],
        features=["Auto oiling", "Digital display", "Multiple pipe sizes"]),
    "Survey Equipment": dict(extrapolated=False, price_range=(75, 300),
        types=["Laser Level", "Total Station", "GPS Rover"],
        modifiers=["Rotary", "Self-Leveling", "Remote Control"],
        purpose_templates=["Ensures precise leveling for construction layouts with a {t}.", "Marks out site boundaries and grades using a {t}.", "Verifies elevation and alignment with a {t}."],
        features=["Self-leveling", "Remote control", "Long battery life"]),
    # -- Categories with zero fixture examples: vocab authored by analogy,
    #    flagged EXTRAPOLATED. Price range falls back to the fixture's
    #    global min/max (25-2500) narrowed to a plausible band for hand
    #    tools vs. vehicles per category, since no empirical anchor exists.
    "Hand Tools": dict(extrapolated=True, price_range=(15, 80),
        types=["Hammer Drill", "Impact Wrench", "Socket Set", "Tool Kit"],
        modifiers=["Cordless", "18V", "Heavy-Duty", "Compact"],
        purpose_templates=["Handles general fastening and assembly tasks with a {t}.", "Provides high-torque output for tough jobs with a {t}.", "Everyday job-site kit built around a {t}."],
        features=["Lithium-ion battery", "Keyless chuck", "LED work light"]),
    "Electrical Tools": dict(extrapolated=True, price_range=(30, 150),
        types=["Cable Tester", "Conduit Bender", "Wire Stripper Set"],
        modifiers=["Digital", "Heavy-Duty", "Portable"],
        purpose_templates=["Tests and diagnoses circuits with a {t}.", "Shapes conduit runs for electrical installs with a {t}.", "Preps and terminates cable with a {t}."],
        features=["Digital display", "Auto-ranging", "Rugged case"]),
    "Automotive Tools": dict(extrapolated=True, price_range=(50, 400),
        types=["Vehicle Hoist", "Tyre Changer", "Diagnostic Scanner"],
        modifiers=["Portable", "Two-Post", "Digital"],
        purpose_templates=["Lifts vehicles for undercarriage work with a {t}.", "Services tyres quickly with a {t}.", "Diagnoses vehicle faults with a {t}."],
        features=["Digital display", "Heavy duty base", "Quick release"]),
    "Measuring Tools": dict(extrapolated=True, price_range=(20, 200),
        types=["Laser Distance Meter", "Digital Caliper", "Survey Tape"],
        modifiers=["Digital", "Long-Range", "Precision"],
        purpose_templates=["Measures distance and dimensions with a {t}.", "Verifies precise tolerances on-site with a {t}.", "Records site measurements quickly with a {t}."],
        features=["Digital display", "Long battery life", "Rugged case"]),
    "Fastening Tools": dict(extrapolated=True, price_range=(20, 150),
        types=["Nail Gun", "Rivet Gun", "Screw Gun"],
        modifiers=["Pneumatic", "Cordless", "Heavy-Duty"],
        purpose_templates=["Drives fasteners quickly with a {t}.", "Speeds up framing and finishing with a {t}.", "Handles high-volume fastening with a {t}."],
        features=["Quick change chuck", "Depth adjustment", "Lightweight frame"]),
    "Garden Tools": dict(extrapolated=True, price_range=(20, 150),
        types=["Hedge Trimmer", "Leaf Blower", "Rotary Tiller"],
        modifiers=["Petrol", "Cordless", "Walk-Behind"],
        purpose_templates=["Maintains gardens and small landscapes with a {t}.", "Clears leaves and debris with a {t}.", "Preps garden beds for planting with a {t}."],
        features=["Lightweight frame", "Ergonomic handle", "Low noise operation"]),
    "Kitchen Equipment": dict(extrapolated=True, price_range=(30, 250),
        types=["Commercial Oven", "Catering Urn", "Chest Freezer"],
        modifiers=["Stainless Steel", "Portable", "Large Capacity"],
        purpose_templates=["Caters for events and large gatherings with a {t}.", "Keeps food hot or cold on-site with a {t}.", "Handles high-volume catering with a {t}."],
        features=["Stainless steel body", "Large capacity", "Easy cleaning"]),
    "Party & Event": dict(extrapolated=False, price_range=(35, 300),
        types=["Marquee", "PA Sound System", "Portable Stage"],
        modifiers=["6x6m", "Large Capacity", "Portable"],
        purpose_templates=["Covers outdoor events and gatherings with a {t}.", "Provides sound and lighting for events with a {t}.", "Sets up a performance area quickly with a {t}."],
        features=["Quick assembly", "Weather resistant", "Easy transport"]),
    "Sports Equipment": dict(extrapolated=True, price_range=(15, 120),
        types=["Portable Goal Post", "Scoreboard", "Sports Netting Kit"],
        modifiers=["Portable", "Heavy-Duty", "Adjustable"],
        purpose_templates=["Sets up a playing field quickly with a {t}.", "Scores and times matches with a {t}.", "Marks out a sports court with a {t}."],
        features=["Quick assembly", "Weather resistant", "Easy transport"]),
    "Other": dict(extrapolated=False, price_range=(25, 300),
        types=["Utility Trailer", "Storage Container", "Generator Trailer"],
        modifiers=["Portable", "Heavy-Duty", "Lockable"],
        purpose_templates=["General-purpose {t} for miscellaneous job-site needs.", "Flexible {t} for tasks outside the standard categories.", "Supports on-site logistics with a {t}."],
        features=["Weather resistant", "Lockable", "Heavy duty frame"]),
}

# 48 distinct Auckland place names from the fixture (PopulateFirebase.js),
# used as-is since the fixture shows 48/48 unique locations -- no repeat
# frequency to model, so this is sampled as a flat list (DISTRIBUTIONS.md).
LOCATIONS = [
    "South Auckland", "West Auckland", "North Shore", "Central Auckland", "East Tamaki",
    "Manukau", "Penrose", "Glenfield", "Mount Wellington", "Henderson", "Newmarket",
    "Botany", "Papatoetoe", "Albany", "Onehunga", "Drury", "Pukekohe", "Mangere",
    "Mt Roskill", "Avondale", "Ellerslie", "Howick", "Papakura", "Te Atatu", "Panmure",
    "Glen Eden", "Pakuranga", "Rosedale", "Warkworth", "Point Chevalier", "Remuera",
    "Flatbush", "Greenlane", "Parnell", "Eden Terrace", "Meadowbank", "Titirangi",
    "Mangere East", "Lynfield", "Kelston", "Epsom", "Mt Albert", "Sandringham",
    "Massey", "Blockhouse Bay", "Mission Bay", "Herne Bay", "Grey Lynn",
]

OWNER_NAME_TEMPLATES = [
    "{w} Equipment", "{w} Rentals", "{w} Ltd", "{w} Pro", "{w} Services",
    "{w} Solutions", "{w} Masters", "{w} Group",
]
# ─── Continuous numeric spec per category ─────────────────────────────────
# (unit, low, high, decimals). Mirrors the fixture's own style of embedding a
# spec number in the name -- e.g. "Excavator (70-ton)", "Power Drill
# (Cordless, 18V)" (PopulateFirebase.js). Values are drawn from a continuous
# range rather than an enumerated list specifically so name/description text
# doesn't collapse into a handful of exact duplicates once corpus size grows
# past the vocabulary's combinatorial capacity -- see near-duplicate check in
# DISTRIBUTIONS.md. Authored, not mined: plausible spec ranges for the
# category, not measured from anywhere.
SPEC_RANGES = {
    "Construction Equipment": ("ton", 5, 80, 1),
    "Material Handling": ("lb", 2000, 8000, 0),
    "Aerial Equipment": ("ft", 15, 65, 1),
    "Concrete Equipment": ("cu yd", 1, 4, 2),
    "Landscaping": ("inch", 4, 24, 1),
    "Transportation": ("ton", 5, 50, 1),
    "Pumps": ("inch", 1, 4, 2),
    "Excavation": ("inch", 6, 36, 1),
    "Compaction": ("kg", 80, 1600, 0),
    "Cutting Tools": ("inch", 4, 16, 1),
    "Air Tools": ("CFM", 80, 400, 0),
    "Power Generation": ("kW", 2, 50, 1),
    "Cranes": ("ton", 20, 120, 0),
    "Demolition Tools": ("J", 15, 45, 1),
    "Safety Equipment": ("m", 2, 20, 1),
    "Welding Equipment": ("A", 100, 400, 0),
    "Cleaning Equipment": ("PSI", 1500, 4000, 0),
    "Surface Preparation": ("inch", 4, 20, 1),
    "Painting Equipment": ("bar", 100, 250, 0),
    "Plumbing Tools": ("inch", 0.5, 4, 2),
    "Survey Equipment": ("m", 100, 800, 0),
    "Hand Tools": ("V", 12, 24, 1),
    "Electrical Tools": ("V", 12, 240, 0),
    "Automotive Tools": ("ton", 1, 5, 2),
    "Measuring Tools": ("m", 1, 100, 0),
    "Fastening Tools": ("mm", 15, 90, 0),
    "Garden Tools": ("cc", 20, 200, 0),
    "Kitchen Equipment": ("L", 10, 400, 0),
    "Party & Event": ("m", 3, 15, 1),
    "Sports Equipment": ("m", 1, 10, 1),
    "Other": ("kg", 50, 2000, 0),
}

OWNER_WORDS = [
    "MegaDig", "EarthMove", "Ground Works", "Versatile", "Lift", "Sky High",
    "Load Pro", "Compact", "Mix It Up", "Tool Rental", "Up High", "Reach High",
    "Boom Time", "Maximum Reach", "Haul It All", "Terrain", "Big Haul",
    "Foundation Force", "Pump It", "Grind Time", "Trench", "Deep Dig",
    "Roll Smooth", "Cut Right", "Air Force", "Power On", "Mega Power",
    "Crane King", "Break It Down", "Road Masters", "Pump Perfect", "Safe Heights",
    "Weld Pro", "Clean Force", "Chip Away", "Mow Pro", "Hole Diggers",
    "Precision Cuts", "Grind Perfect", "Heat Solutions", "Plaster Pro",
    "Blast Clean", "Spray Masters", "Thread Right", "Level Best",
]


def mulberry32(seed):
    """Small deterministic seeded PRNG (avoids relying on `random`'s
    version-specific stream so the corpus is reproducible across Python
    versions -- documented, not left implicit)."""
    state = seed & 0xFFFFFFFF

    def rng():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rng


def make_record(idx, cat_name, cat, rng):
    types = cat["types"]
    modifiers = cat["modifiers"]
    templates = cat["purpose_templates"]
    features_pool = cat["features"]

    t = types[int(rng() * len(types))]
    style = modifiers[int(rng() * len(modifiers))]
    template = templates[int(rng() * len(templates))]

    unit, lo_spec, hi_spec, decimals = SPEC_RANGES[cat_name]
    spec_val = lo_spec + rng() * (hi_spec - lo_spec)
    spec_val = round(spec_val, decimals) if decimals else int(round(spec_val))
    spec_text = f"{spec_val}{unit}" if unit in ("V", "A", "J") else f"{spec_val} {unit}"

    # 2 name constructions, mirroring the fixture's own mixed styles
    # ("Excavator (70-ton)" spec-only; "Power Drill (Cordless, 18V)"
    # style+spec). Both always include the continuous spec value -- an
    # earlier version also had a style-only branch ("{t} ({style})") with no
    # spec, which had only len(types)*len(modifiers) possible outputs per
    # category (as few as 16) and dominated the exact-duplicate rate at
    # corpus_100000 (17%, see git history). Always including spec keeps the
    # per-category name space bounded below by the spec range's resolution,
    # not by the fixed adjective list (see DISTRIBUTIONS.md near-dup check).
    name = (f"{t} ({spec_text})" if rng() < 0.4
             else f"{t} ({style}, {spec_text})")

    # Exactly 3 features, no replacement, per DISTRIBUTIONS.md (constant=3
    # in the fixture). Falls back to sampling with replacement if a
    # category's pool has fewer than 3 entries.
    pool = list(features_pool)
    feats = []
    for _ in range(3):
        if not pool:
            pool = list(features_pool)
        i = int(rng() * len(pool))
        feats.append(pool.pop(i))

    description = template.format(t=t.lower())
    description = re.sub(r"\ba (?=[aeiouAEIOU])", "an ", description)
    description += f" Rated {spec_text}, with {feats[0].lower()}."

    lo, hi = cat["price_range"]
    rate_per_day = round(lo + rng() * (hi - lo))

    location = LOCATIONS[int(rng() * len(LOCATIONS))]
    owner_template = OWNER_NAME_TEMPLATES[int(rng() * len(OWNER_NAME_TEMPLATES))]
    owner_word = OWNER_WORDS[int(rng() * len(OWNER_WORDS))]
    owner_name = owner_template.format(w=owner_word)

    return {
        "id": f"synthetic-{idx:07d}",
        "name": name,
        "description": description,
        "category": cat_name,
        "ratePerDay": rate_per_day,
        "location": location,
        "features": feats,
        "ownerName": owner_name,
        "_category_extrapolated": cat["extrapolated"],
    }


def generate_stream(n, seed):
    rng = mulberry32(seed)
    cat_names = list(CATEGORIES.keys())
    records = []
    for i in range(n):
        cat_name = cat_names[int(rng() * len(cat_names))]
        cat = CATEGORIES[cat_name]
        records.append(make_record(i, cat_name, cat, rng))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000],
                         help="Corpus sizes to emit (records). Each size's output is a "
                              "prefix of the largest requested size's stream -- strict "
                              "superset property, not independently generated.")
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT,
                         help="PRNG seed. Recorded in PROVENANCE.md; changing it "
                              "invalidates prior measurements against this corpus.")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    max_n = max(args.sizes)
    full_stream = generate_stream(max_n, args.seed)

    for n in sorted(args.sizes):
        out_path = args.out_dir / f"corpus_{n}.jsonl"
        with out_path.open("w") as f:
            for rec in full_stream[:n]:
                f.write(json.dumps(rec) + "\n")
        print(f"Wrote {n} records -> {out_path} (seed={args.seed})")


if __name__ == "__main__":
    main()
