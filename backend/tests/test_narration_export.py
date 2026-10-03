import pytest

from app.services.narration_export import export_narration


def test_clean_export_contains_only_nonempty_scene_narration_in_order():
    script = {
        "title": "Not exported",
        "scenes": [
            {"narration": "  First spoken line.  ", "imagePrompt": "not exported", "delivery": "dramatic"},
            {"narration": "", "caption": "not exported"},
            {"narration": "Second spoken line.", "delivery": "pause"},
        ],
    }

    assert export_narration(script, "clean") == "First spoken line.\n\nSecond spoken line."
    assert script["scenes"][0]["narration"] == "  First spoken line.  "


def test_expressive_export_adds_only_supported_generic_delivery_cues():
    script = {
        "scenes": [
            {"narration": "Start here.", "delivery": "dramatic"},
            {"narration": "Ignore this cue.", "delivery": "elevenlabs:whisper"},
            {"narration": "Finish here.", "delivery": "pause"},
        ]
    }

    assert export_narration(script, "expressive") == "[dramatic] Start here.\n\nIgnore this cue.\n\n[pause] Finish here."


@pytest.mark.parametrize("delivery", [["dramatic"], {"cue": "dramatic"}])
def test_expressive_export_omits_malformed_delivery_metadata(delivery):
    script = {"scenes": [{"narration": "Only the spoken text.", "delivery": delivery}]}

    assert export_narration(script, "expressive") == "Only the spoken text."


def test_export_rejects_unknown_style():
    with pytest.raises(ValueError, match="unsupported narration export style"):
        export_narration({"scenes": []}, "ssml")
