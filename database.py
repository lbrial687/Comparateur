"""
Connexion à la base de données PostgreSQL (hébergée sur Render).

Sur Render, une fois votre base PostgreSQL créée, Render vous donne une
"Internal Database URL" à mettre dans une variable d'environnement
DATABASE_URL sur votre service web ET sur votre cron job.

En local, vous pouvez créer un fichier .env avec :
DATABASE_URL=postgresql://user:password@localhost:5432/comparateur_vols
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "La variable d'environnement DATABASE_URL n'est pas définie. "
        "Ajoutez-la dans les paramètres de votre service Render "
        "(ou dans un fichier .env en local)."
    )

# Render fournit parfois une URL qui commence par "postgres://" au lieu de
# "postgresql://" — SQLAlchemy récent exige "postgresql://", donc on corrige.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    À utiliser avec FastAPI (Depends(get_db)) : ouvre une connexion,
    la donne à la route, puis la referme automatiquement même en cas d'erreur.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
