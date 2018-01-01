from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

eng = create_engine('sqlite:///media.db')
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
    offset = Column('offset', Integer)
    prettyname = Column('prettyname', String, nullable=True)
    duration = Column('duration', Integer)
    grandparentRatingKey = Column('grandparentRatingKey', Integer)
    location = Column('location', String, nullable=True)
    updatedAt = Column('updatedAt ', DateTime, nullable=True)

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
