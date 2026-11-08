"""Profile, glyph reader and banner locate on rendered synthetic overlays (phase 2.2b)."""

import json

import numpy as np
import pytest

from alea.video.overlay.glyphs import GlyphSet, read_number
from alea.video.overlay.locate import (
    find_overlay,
    locate_anchor,
    overlay_present,
    roi_pixels,
    to_gray,
)
from alea.video.overlay.profile import (
    OverlayProfile,
    ProfileError,
    Roi,
    default_template_profile,
)
from alea.video.overlay.synth import (
    make_synthetic_profile,
    render_frame,
    render_roi_gray,
    synthetic_layout,
)

cv2 = pytest.importorskip("cv2")

SIZE = (320, 180)
ZERO = {"red": 0, "blue": 0}


@pytest.fixture(scope="module", params=["top", "bottom"])
def profile(request):
    return make_synthetic_profile(request.param)


def test_glyph_round_trip_with_noise(profile):
    rng = np.random.default_rng(7)
    glyphs = GlyphSet.from_entries(profile.glyphs)
    ok = total = 0
    for roi_name, texts in (
        ("red_score", [str(d) for d in range(10)] + ["41", "07", "75", "63", "95"]),
        ("clock", ["2:30", "1:59", "0:00", "2:08", "1:47", "0:36", "0:25", "1:11"]),
        ("blue_lock", ["0", "3", "5"]),
    ):
        for _ in range(15):
            for text in texts:
                gray = render_roi_gray(profile, roi_name, text, rng, noise_sigma=8.0)
                got, _ = read_number(gray, glyphs)
                ok += got == text
                total += 1
    assert ok / total >= 0.99, f"{ok}/{total}"


def test_blank_roi_reads_nothing(profile):
    glyphs = GlyphSet.from_entries(profile.glyphs)
    blank = np.full((20, 30), 30, dtype=np.uint8)
    assert read_number(blank, glyphs) == ("", 0.0)


def test_glyphs_survive_profile_json(profile, tmp_path):
    path = tmp_path / "p.json"
    profile.write(path)
    again = OverlayProfile.read(path)
    gray = render_roi_gray(again, "clock", "1:23", np.random.default_rng(1))
    assert read_number(gray, GlyphSet.from_entries(again.glyphs))[0] == "1:23"
    assert path.stat().st_size < 400_000


def _frame(profile, phase="auto"):
    rng = np.random.default_rng(3)
    return render_frame(
        *SIZE, profile, 150, ZERO, ZERO, {"red": 5, "blue": 5}, "Q1",
        {"red": [1, 2], "blue": [3, 4]}, phase, rng,
    )  # fmt: skip


def test_anchor_located_within_3px(profile):
    gray = to_gray(_frame(profile))
    tpl = profile.anchor.template
    score, x, y, scale = locate_anchor(gray, tpl)
    x0, y0, _, _ = roi_pixels(profile, "banner_anchor", gray.shape)
    assert scale == pytest.approx(1.0)
    assert score > 0.9
    assert abs(x - x0) <= 3 and abs(y - y0) <= 3


def test_anchor_located_at_1p2x_within_6px(profile):
    rng = np.random.default_rng(4)
    scene = rng.integers(30, 90, size=(180, 320), dtype=np.uint8)
    big = cv2.resize(profile.anchor.template, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_LINEAR)
    scene[60 : 60 + big.shape[0], 100 : 100 + big.shape[1]] = big
    score, x, y, scale = locate_anchor(scene, profile.anchor.template)
    assert abs(x - 100) <= 6 and abs(y - 60) <= 6
    assert scale == pytest.approx(1.2)
    assert score > 0.8


def test_overlay_present_and_absent(profile):
    assert overlay_present(_frame(profile), profile)
    rng = np.random.default_rng(5)
    dead = render_frame(*SIZE, profile, None, ZERO, ZERO, ZERO, "", {"red": [], "blue": []},
                        "auto", rng)  # fmt: skip
    assert not overlay_present(dead, profile)
    assert find_overlay(dead, profile) is None


def test_phase_override_moves_score_roi(profile):
    auto = roi_pixels(profile, "red_score", (180, 320), phase="auto")
    teleop = roi_pixels(profile, "red_score", (180, 320), phase="teleop")
    transition = roi_pixels(profile, "red_score", (180, 320), phase="transition")
    assert teleop[0] - auto[0] >= 10
    assert transition == teleop
    # reading the TELEOP frame with the AUTO ROI fails, with the TELEOP ROI works
    glyphs = GlyphSet.from_entries(profile.glyphs)
    rng = np.random.default_rng(8)
    frame = render_frame(*SIZE, profile, 100, {"red": 41, "blue": 7}, ZERO, {"red": 5, "blue": 5},
                         "Q1", {"red": [1], "blue": [2]}, "teleop", rng)  # fmt: skip
    gray = to_gray(frame)
    x0, y0, x1, y1 = teleop
    assert read_number(gray[y0:y1, x0:x1], glyphs, "0123456789")[0] == "41"


def test_roi_pixels_follows_anchor_shift(profile):
    base = roi_pixels(profile, "clock", (180, 320))
    nx, ny = profile.anchor.nominal_xy_px(320, 180)
    shifted = roi_pixels(profile, "clock", (180, 320), anchor=(0.9, nx + 7, ny + 4, 1.0))
    assert shifted[0] - base[0] == 7 and shifted[1] - base[1] == 4


def test_second_layout_differs_from_first():
    top, bottom = synthetic_layout("top"), synthetic_layout("bottom")
    assert bottom.roi("clock").y0 > 0.5 > top.roi("clock").y0


# --- profile JSON -----------------------------------------------------------------------------


def test_profile_round_trip_and_validation(tmp_path):
    prof = default_template_profile("rt")
    path = tmp_path / "p.json"
    prof.write(path)
    again = OverlayProfile.read(path)
    assert again.to_dict() == prof.to_dict()
    assert again.roi("red_score", "teleop") != again.roi("red_score", "auto")
    assert again.roi("clock", "post") == again.roi("clock")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d["layout"].pop("clock"),
        lambda d: d["layout"].update(clock={"x0": 0.6, "y0": 0.1, "x1": 0.4, "y1": 0.2}),
        lambda d: d["layout"].update(bogus=d["layout"]["clock"]),
        lambda d: d["phase_layouts"].update(sideways={}),
        lambda d: d["glyphs"].append({"char": "ab", "template": [[1]], "shape": [1, 1]}),
        lambda d: d["glyphs"].append({"char": "a", "template": [[300]], "shape": [1, 1]}),
        lambda d: d["glyphs"].append({"char": "a", "template": [[1]], "shape": [2, 2]}),
    ],
)
def test_profile_rejects_bad_files(mutate):
    d = default_template_profile().to_dict()
    mutate(d)
    with pytest.raises(ProfileError):
        OverlayProfile.from_dict(d)


def test_profile_rejects_non_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(ProfileError):
        OverlayProfile.read(path)
    assert Roi(0, 0, 1, 1).to_dict()["x1"] == 1
