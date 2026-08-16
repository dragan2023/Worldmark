from pathlib import Path


def test_itinerary_form_submits_directly_to_the_final_itinerary_endpoint():
    template = Path("app/templates/itineraries/form.html").read_text(encoding="utf-8")
    script = Path("app/static/js/itinerary-form.js").read_text(encoding="utf-8")

    assert "itinerary-form.js?v=final-itinerary-v1" in template
    assert "/api/v1/itineraries/finalize" in script
    assert "/choice-preview" not in script
    assert "meituan_plan_content" not in script
    assert "data.transport.legs" not in script
    assert "data.lodging.cities" not in script
