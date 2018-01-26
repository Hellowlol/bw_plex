import os
from contextlib import contextmanager

from sqlalchemy import create_engine, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from bw_plex import DEFAULT_FOLDER

DB_PATH = os.path.join(DEFAULT_FOLDER, 'media.db')

eng = create_engine('sqlite:///' + DB_PATH)
session_factory = sessionmaker(bind=eng)
sess = scoped_session(session_factory)
Base = declarative_base()


class Preprocessed(Base):
    """Table for preprocessed stuff."""
    __tablename__ = "preprocessed"

    id = Column(Integer, primary_key=True)
    show_name = Column('show_name', String)
    ep_title = Column('ep_title', String)
    ratingKey = Column('ratingKey', Integer)
    theme_end = Column('theme_end', Integer)
    theme_end_str = Column('theme_end_str', String)
    theme_start = Column('theme_start', Integer)
    theme_start_str = Column('theme_start_str', String)
    correct_time_start = Column('correct_time_start', String, nullable=True)  # This for manual override.
    correct_time_end = Column('correct_time_end', String, nullable=True)  # This for manual override.
    prettyname = Column('prettyname', String, nullable=True)
    duration = Column('duration', Integer)
    grandparentRatingKey = Column('grandparentRatingKey', Integer)
    location = Column('location', String, nullable=True)
    updatedAt = Column('updatedAt ', DateTime, nullable=True)
    has_recap = Column('has_recap', Boolean, nullable=True)


# Create db.
Base.metadata.create_all(eng)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = sess()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()
