from corgidrp_gui.core.values import format_value, parse_value, values_equal


def test_parse_round_trips():
    assert parse_value("1.0") == 1.0 and isinstance(parse_value("1.0"), float)
    assert parse_value("3") == 3 and isinstance(parse_value("3"), int)
    assert parse_value("True") is True and parse_value("false") is False
    assert parse_value("None") is None and parse_value("null") is None
    assert parse_value("[1, 2]") == [1, 2] and parse_value("(1, 2)") == (1, 2)
    assert parse_value("'image'") == "image" and parse_value('"image"') == "image"
    assert parse_value("image") == "image"
    assert parse_value("ISACQ", "str") == "ISACQ" and parse_value("12", "str") == "12"
    assert parse_value('["ISACQ"]', "list of str") == ["ISACQ"]
    assert parse_value("auto", "int or 'auto'") == "auto"


def test_format_and_equal():
    assert format_value(True) == "True" and format_value(None) == "None"
    assert format_value("image") == "'image'" and format_value([1, 2]) == "[1, 2]"
    assert format_value(1.0) == "1.0"
    assert values_equal(1, 1.0) and values_equal([1], (1,)) and not values_equal(True, 1)
    for v in (1.5, 2, "x", None, True, [1, "a"], {"k": 1}):
        assert values_equal(parse_value(format_value(v)), v), v
