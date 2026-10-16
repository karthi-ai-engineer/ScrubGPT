"""A1/A3 IDs against the Phase 0 fixture reference (criterion 12 of the A1-A4 brief; D-051, #11).

D-051: "the YAML IDs follow the fixture rarp.json". #11 (Team Lead): these permanent tests read
`contracts/fixtures/reference/rarp.json` from the working tree as plain JSON, with no contracts
import and no `git show`. Before `contracts-v1.0` the file isn't on `dev1/b1`, so they skip with a
reason naming the tag, and the criterion is reported BLOCKED until main is merged after the tag.

`T1_REFERENCE_FIXTURE_OVERRIDE` (a path) lets Tester 1 run the same comparison once by hand
against a copy of the fixture taken from `p0/contracts` (#11 "informational"); it is never set in
CI, and without it the working-tree file is the only one read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

TAG = "contracts-v1.0"


@pytest.fixture(scope="module")
def reference(const) -> dict:
    override = os.environ.get("T1_REFERENCE_FIXTURE_OVERRIDE")
    path = Path(override) if override else const.reference_fixture_path
    if not path.is_file():
        pytest.skip(
            f"{const.reference_fixture_path.relative_to(const.repo_root).as_posix()} is not on "
            f"this branch before the {TAG} tag (D-051, #11): criterion 12 is BLOCKED until main "
            f"is merged into dev1/b1 after {TAG}"
        )
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _bilingual(value) -> tuple:
    return (value.get("ja"), value.get("en")) if isinstance(value, dict) else (value,)


def test_c12_phase_ids_and_names_equal_the_fixture(reference, phases):
    """C12 "phase … ids and names … equal those in contracts/fixtures/reference/rarp.json"
    (D-051 "the YAML IDs follow the fixture rarp.json"), in order."""
    expected = [(p["id"], _bilingual(p["name"])) for p in reference["phases"]]
    actual = [(p.get("id"), _bilingual(p.get("name"))) for p in phases]
    assert actual == expected


def test_c12_step_ids_and_names_equal_the_fixture(reference, phases):
    """C12 "step … ids and names … equal those in" the fixture reference, phase by phase, in
    order (D-051)."""
    expected = {
        p["id"]: [(s["id"], _bilingual(s["name"])) for s in p["steps"]] for p in reference["phases"]
    }
    actual = {
        p.get("id"): [(s.get("id"), _bilingual(s.get("name"))) for s in p.get("steps") or []]
        for p in phases
    }
    assert actual == expected


def test_c12_checkpoint_ids_and_texts_equal_the_fixture(reference, phases):
    """C12 "checkpoint ids and names … equal those in" the fixture reference (a checkpoint's
    name is its `text`, plan §4.2b), step by step (D-051)."""
    expected = {
        s["id"]: [(c["id"], _bilingual(c["text"])) for c in s["checkpoints"]]
        for p in reference["phases"]
        for s in p["steps"]
    }
    actual = {
        s.get("id"): [(c.get("id"), _bilingual(c.get("text"))) for c in s.get("checkpoints") or []]
        for p in phases
        for s in p.get("steps") or []
    }
    assert actual == expected


def test_c12_obstacle_families_equal_the_fixture(reference, taxonomy):
    """C12 "obstacle families … equal those in" the fixture reference: ids and names, in order
    (D-051)."""
    expected = [(f["id"], _bilingual(f["name"])) for f in reference["obstacle_taxonomy"]]
    actual = [(f.get("id"), _bilingual(f.get("name"))) for f in taxonomy["families"]]
    assert actual == expected


def test_c12_obstacle_leaves_equal_the_fixture(reference, taxonomy):
    """C12 "obstacle … leaves equal those in" the fixture reference: the same leaf ids under each
    family, with the same names (D-051). Leaf order carries no meaning (§4.2b), so it is not
    compared."""
    expected = {
        f["id"]: {leaf["id"]: _bilingual(leaf["name"]) for leaf in f["leaves"]}
        for f in reference["obstacle_taxonomy"]
    }
    actual = {
        f.get("id"): {
            leaf.get("id"): _bilingual(leaf.get("name")) for leaf in f.get("leaves") or []
        }
        for f in taxonomy["families"]
    }
    assert actual == expected
