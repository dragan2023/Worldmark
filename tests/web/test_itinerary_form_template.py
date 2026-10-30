from pathlib import Path


def test_itinerary_form_defaults_to_basic_endpoint_with_optional_enhancement():
    """B07：页面默认走基础规划（无需密钥），外部增强是显式可选项。"""
    template = Path("app/templates/itineraries/form.html").read_text(encoding="utf-8")
    script = Path("app/static/js/itinerary-form.js").read_text(encoding="utf-8")

    assert "itinerary-form.js?v=2" in template
    assert 'id="use-enhancement"' in template
    assert "/api/v1/itineraries/finalize" in script  # 仅在勾选增强时使用
    assert "const endpoint = enhanced ? '/api/v1/itineraries/finalize' : '/api/v1/itineraries'" in script
    assert "/choice-preview" not in script
    assert "meituan_plan_content" not in script
    assert "data.transport.legs" not in script
    assert "data.lodging.cities" not in script
