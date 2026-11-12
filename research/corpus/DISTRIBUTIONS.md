# Listing Schema and Field Distributions

Source of truth for `generate_corpus.py`. Extracted, not estimated. Every number
below is computed directly from code, not guessed.

## Provenance of the schema

- Collection name in Firestore: `"equipment"` (not `"listings"` — that word is UI/AI-service terminology only). `src/services/equipmentService.js`, `src/components/Dashboard/AddEquipment.js:238`, `firestore.rules:66-89`.
- Field shape (write path), `src/components/Dashboard/AddEquipment.js:203-233`:
  `name, description, category, ratePerDay, location, features[], imageUrl, ownerId, ownerName, available, approvalStatus, isApproved, status, views, bookings, totalRevenue, rating, reviews, createdAt, updatedAt`.
  No `size`/`dimensions` field exists in the app. `condition` and `tags` are proposed by the AI draft generator (`src/services/aiListingService.js:9-24`) but dropped by the submit handler — not persisted, not present in production reads (`src/components/Equipment/EquipmentDetail.js:171-340`).
- Category taxonomy: fixed 31-item enum, `src/components/Dashboard/AddEquipment.js:54-87`. Full list: Power Tools, Construction Equipment, Material Handling, Aerial Equipment, Concrete Equipment, Landscaping, Transportation, Pumps, Excavation, Compaction, Cutting Tools, Air Tools, Power Generation, Cranes, Demolition Tools, Safety Equipment, Welding Equipment, Cleaning Equipment, Surface Preparation, Painting Equipment, Plumbing Tools, Survey Equipment, Hand Tools, Electrical Tools, Automotive Tools, Measuring Tools, Fastening Tools, Garden Tools, Kitchen Equipment, Party & Event, Sports Equipment, Other.
- Form validation, `AddEquipment.js:128-155`: `name`, `description`, `category`, `location` required non-empty; `ratePerDay > 0`. No `maxLength` enforced at form level.
- AI-draft coercion bounds (not enforced on the manual form, only when AI-assisted), `aiListingService.js:9-24`: `title` ≤ 80 chars, `description` ≤ 600 chars, `location` ≤ 60 chars, `pricePerDay` clamped 5–500 NZD.

## Empirical distributions — n = 48

Source: `sampleEquipment` array, `src/components/admin/PopulateFirebase.js:15-583`. This is developer-authored fixture data loaded through an admin-only "populate demo data" tool, **not real user-generated content** — RentMate is pre-launch (see AUDIT.md). It is the only listing-shaped dataset that exists in the repository, so it is the best available basis for a *plausible* synthetic distribution, not a claim about real usage. State this limitation in the paper.

| Field | n | min | median | mean | max |
|---|---|---|---|---|---|
| `name` — char length | 48 | 13 | 22 | 22.4 | 34 |
| `name` — word count | 48 | 2 | 3 | 3.1 | 5 |
| `description` — char length | 48 | 31 | 49 | 48.2 | 72 |
| `description` — word count | 48 | 4 | 7 | 7.0 | 10 |
| `features[]` — item count | 48 | 3 | 3 | 3.0 | 3 |
| `ratePerDay` (NZD) | 48 | 25 | 220 | 431.6 | 2500 |

Notes on these numbers, stated plainly for the limitations section:
- `description` in the seed data is a single short sentence (median 7 words / 49 chars) — far shorter than the plan's assumption of "description length in tokens" implying multi-sentence listing copy. Any synthetic corpus matching this distribution will produce very short documents; retrieval over 7-word descriptions is a materially different (easier, lower-entropy) task than retrieval over paragraph-length listings. This must be stated as a property of the fixture data, not softened.
- `features[]` count is **constant at exactly 3** for all 48 items — this is a fixture-authoring artifact (whoever wrote the seed data always typed exactly three bullet features), not a real distribution. Do not sample a distribution over this field; treat it as a fixed count = 3 in the generator, and say so.
- `ratePerDay` is heavy-tailed (25–2500, mean pulled up by cranes/excavators). Median (220) is a better central-tendency figure to cite than mean.
- **Category coverage is incomplete**: only 23 of the 31 defined categories appear in the 48-item sample (`distinct categories used: 23 of 31`, computed directly). 8 categories (Hand Tools, Electrical Tools, Automotive Tools, Measuring Tools, Fastening Tools, Garden Tools, Kitchen Equipment, Sports Equipment) have zero fixture examples — no empirical description/name style to draw from for those. The generator must either exclude them, or extrapolate their style from the closest populated category and say so explicitly.
- **Data quality issue in the fixture, noted not silently corrected**: one item uses category `"Construction Tools"`, which is not a member of the 31-item enum defined in `AddEquipment.js:54-87` (closest valid entries are "Construction Equipment" or "Hand Tools"). This is a pre-existing bug in the seed data. Treated as a single mislabeled outlier for distribution purposes (excluded from the 23-of-31 coverage count above, which only counts valid enum categories), not corrected in-place since that would misrepresent what the app's own fixture data actually contains.
- Category frequency (raw counts, n=48, excludes the 1 invalid "Construction Tools" outlier): Construction Equipment 7, Aerial Equipment 4, Power Tools 3, Transportation 3, Landscaping 3, Excavation 3, Compaction 3, Cutting Tools 3, Material Handling 2, Concrete Equipment 2, Power Generation 2, Cranes 2, Pumps 1, Air Tools 1, Demolition Tools 1, Safety Equipment 1, Welding Equipment 1, Cleaning Equipment 1, Surface Preparation 1, Painting Equipment 1, Plumbing Tools 1, Survey Equipment 1.
- `location`: 48/48 distinct values (all Auckland suburbs/areas) — every item has a unique location string in the fixture, so there's no meaningful repeat-frequency distribution to sample from; treat as draws from a flat list of Auckland place names.

## Vocabulary

Implemented in `generate_corpus.py` (`CATEGORIES`, `SPEC_RANGES`): per-category equipment type nouns, style modifiers, purpose-sentence templates, and a feature pool, all seeded from the fixture's own naming style (e.g. "Excavator (70-ton)", "Power Drill (Cordless, 18V)"). 23 of 31 categories are drawn from real fixture examples; 8 are authored by analogy and flagged `extrapolated=True` in code and per-record (`_category_extrapolated`). See `CORPUS_REPORT.md` for the resulting duplicate/near-duplicate rates.

## Honesty statement for the paper (per plan §2 Phase 2)

The corpus is synthetic because RentMate is pre-launch with no real listings (AUDIT.md). Its field-length and category distributions are anchored to a 48-item developer fixture, not production data — a fixture that is itself narrow (constant feature count, incomplete category coverage, one mislabeled category, single-sentence descriptions). Scaling this narrow distribution to 1k–500k documents via templated combinatorial generation will produce a corpus with lower vocabulary diversity and shorter, more uniform documents than organic listing text would have, which likely makes retrieval look easier than production would. State this prominently in limitations, not softened.
