from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

from app.db.orm.posts import Post, IngestCursor


class PostRepository:
    def __init__(self, engine):
        self.engine = engine

    def upsert_posts(self, posts_data: list[dict]) -> int:
        if not posts_data:
            return 0
        with Session(self.engine) as session, session.begin():
            statement = insert(Post).values(posts_data)
            session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[Post.uri]
                )
            )
        return len(posts_data)

    def get_cursor(self, stream: str) -> int:
        with Session(self.engine) as session:
            cursor = session.scalar(select(IngestCursor.cursor).where(IngestCursor.stream == stream))
            return cursor or 0

    def set_cursor(self, stream: str, cursor: int):
        with Session(self.engine) as session, session.begin():
            statement = insert(IngestCursor).values({"stream": stream, "cursor": cursor})
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[IngestCursor.stream],
                    set_={"cursor": statement.excluded.cursor}
                )
            )

    def count_posts(self) -> int:
        from sqlalchemy import func
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Post))
