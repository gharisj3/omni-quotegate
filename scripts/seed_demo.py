from app.database import Base, SessionLocal, engine
from app.seed import reset_and_seed


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        reset_and_seed(db)
    print("Demo data seeded.")


if __name__ == "__main__":
    main()
