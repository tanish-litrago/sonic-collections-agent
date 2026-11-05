import os
from datetime import date

def today() -> date:
    v = os.getenv("DEMO_TODAY")
    return date.fromisoformat(v) if v else date.today()
