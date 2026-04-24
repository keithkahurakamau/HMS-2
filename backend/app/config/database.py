from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config.settings import settings

# Create the SQLAlchemy Engine
engine = create_engine(settings.DATABASE_URL)

# Create a SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create the Base class for our models to inherit from
Base = declarative_base()

# Dependency to get the DB session in our routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()