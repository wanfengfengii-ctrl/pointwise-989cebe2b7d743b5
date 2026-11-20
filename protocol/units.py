THICKNESS_UNITS = frozenset(('nm', 'μm', 'mm'))


def validate_unit(unit: str) -> str:
    if not isinstance(unit, str) or unit not in THICKNESS_UNITS:
        raise ValueError('unit must be nm, μm or mm')
    return unit
