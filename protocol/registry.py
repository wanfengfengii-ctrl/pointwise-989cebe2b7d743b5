import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from protocol.levels import LevelOrder, require_identifier, validate_levels
from protocol.rationals import encode_rational, parse_rational
from protocol.units import validate_unit


@dataclass(frozen=True)
class ProtocolRule:
    version_id: int
    protocol_id: str
    levels: LevelOrder
    unit: str
    lower: Fraction
    upper: Fraction


def initialize_rules(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS protocol_rules (
            version_id INTEGER PRIMARY KEY,
            protocol_id TEXT NOT NULL,
            levels TEXT NOT NULL,
            unit TEXT NOT NULL,
            lower_value TEXT NOT NULL,
            upper_value TEXT NOT NULL
        )
    ''')


def _rule_inputs(protocol_id, levels, unit, lower, upper):
    name = require_identifier(protocol_id, 'protocol_id')
    order = validate_levels(levels)
    unit_code = validate_unit(unit)
    lower_value = parse_rational(lower)
    upper_value = parse_rational(upper)
    if lower_value > upper_value:
        raise ValueError('rule bounds are reversed')
    return name, order, unit_code, lower_value, upper_value


def register_protocol(connection, protocol_id, levels, unit, lower, upper) -> ProtocolRule:
    fields = _rule_inputs(protocol_id, levels, unit, lower, upper)
    name, order, unit_code, lower_value, upper_value = fields
    cursor = connection.execute('''
        INSERT INTO protocol_rules (protocol_id, levels, unit, lower_value, upper_value)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, json.dumps(order.labels, ensure_ascii=False), unit_code,
          encode_rational(lower_value), encode_rational(upper_value)))
    return ProtocolRule(cursor.lastrowid, *fields)


def get_rule(connection, version_id: int) -> ProtocolRule:
    if type(version_id) is not int or not 1 <= version_id < 2**63:
        raise LookupError('unknown protocol version')
    row = connection.execute('''
        SELECT protocol_id, levels, unit, lower_value, upper_value
        FROM protocol_rules WHERE version_id = ?
    ''', (version_id,)).fetchone()
    if row is None:
        raise LookupError(f'unknown protocol version: {version_id}')
    protocol_id, levels, unit, lower, upper = row
    return ProtocolRule(version_id, *_rule_inputs(protocol_id, json.loads(levels), unit, lower, upper))
