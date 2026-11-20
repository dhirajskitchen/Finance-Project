from alembic import context

import app.models  # noqa: F401
from app.core.db import Base, engine

target_metadata = Base.metadata

with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
