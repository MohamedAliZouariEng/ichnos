"""chunks full-text index (FTS5, ADR-0008)

Revision ID: b2f0c1a9d3e4
Revises: 8447ca40f5f4
Create Date: 2026-09-19

Written by hand: Alembic cannot autogenerate FTS5 virtual tables or triggers.
The triggers keep chunks_fts in step with chunks on every insert, update and delete.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2f0c1a9d3e4"
down_revision: str | None = "8447ca40f5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            heading, text, content='chunks', content_rowid='id', tokenize='porter unicode61'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, heading, text) VALUES (new.id, new.heading, new.text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, heading, text)
            VALUES ('delete', old.id, old.heading, old.text);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, heading, text)
            VALUES ('delete', old.id, old.heading, old.text);
            INSERT INTO chunks_fts(rowid, heading, text) VALUES (new.id, new.heading, new.text);
        END
        """
    )


def downgrade() -> None:
    for trigger in ("chunks_au", "chunks_ad", "chunks_ai"):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP TABLE IF EXISTS chunks_fts")
