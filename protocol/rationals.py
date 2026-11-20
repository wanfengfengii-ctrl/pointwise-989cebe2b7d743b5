from fractions import Fraction


def parse_rational(value) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError('invalid rational value') from exc
    raise ValueError('expected an integer, Fraction or rational string')


def encode_rational(value: Fraction) -> str:
    return str(parse_rational(value))
