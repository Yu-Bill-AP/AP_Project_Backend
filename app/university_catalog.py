"""Official-policy review for international first-year U.S. applicants.

The JSON catalogue is maintained per school, with policy-specific official URLs,
review dates, entry-year coverage, and explicit unresolved fields. Planner
academic targets and major strengths are internal research signals, never
published admissions cutoffs. No network requests occur while serving matches.
"""

import json
from pathlib import Path
from typing import Any


_CATALOG = json.loads(Path(__file__).with_name("university_requirements.json").read_text(encoding="utf-8"))
CATALOG_VERSION = _CATALOG["catalogVersion"]
LAST_REVIEWED = _CATALOG["checkedAt"]
DEFAULT_ENTRY_YEAR = _CATALOG["defaultEntryYear"]
US_UNIVERSITY_CATALOG: list[dict[str, Any]] = _CATALOG["schools"]
UNIVERSITY_BY_NAME = {school["name"]: school for school in US_UNIVERSITY_CATALOG}
if len(UNIVERSITY_BY_NAME) != _CATALOG["schoolCount"]:
    raise ValueError("University catalogue has duplicate or missing schools")

# Retained for consumers that use the catalogue's internal reference bands.
PLANNER_TARGETS = {
    "ultra": {"unweightedGpa": 3.90, "sat": 1520},
    "high": {"unweightedGpa": 3.80, "sat": 1450},
    "selective": {"unweightedGpa": 3.65, "sat": 1350},
}
TRACKS = ("计算机", "工程", "商科", "生物医学", "人文社科", "艺术")
