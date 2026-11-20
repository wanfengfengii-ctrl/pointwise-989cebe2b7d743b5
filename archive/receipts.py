import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicationReceipt:
    artifact_id: int
    receipt_id: str


def make_receipt(artifact_id: int) -> PublicationReceipt:
    return PublicationReceipt(artifact_id, f'R-{artifact_id}')


def insert_receipt(connection: sqlite3.Connection, receipt: PublicationReceipt) -> None:
    connection.execute('''
        INSERT INTO publication_receipts (artifact_id, receipt_id) VALUES (?, ?)
    ''', (receipt.artifact_id, receipt.receipt_id))


def find_receipt(connection: sqlite3.Connection, artifact_id: int) -> PublicationReceipt | None:
    row = connection.execute('''
        SELECT artifact_id, receipt_id FROM publication_receipts WHERE artifact_id = ?
    ''', (artifact_id,)).fetchone()
    return None if row is None else PublicationReceipt(*row)
