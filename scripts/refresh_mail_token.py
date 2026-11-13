"""Daily refresh of the sender-mailbox sign-in (deploy/mockinterview-mailrefresh.*).

Microsoft keeps a sign-in alive as long as it is used; this uses it once a day so
it does not lapse between assessment sessions. Exit 1 when an admin must reconnect.

    python scripts/refresh_mail_token.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.services import mailer  # noqa: E402

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    print("mailbox:", mailer.keep_alive(db))
except mailer.NeedsReconnect as e:
    print("mailbox: an admin must reconnect (Admin -> 发件邮箱):", e)
    sys.exit(1)
except mailer.MailError as e:
    print("mailbox: refresh failed, will retry tomorrow:", e)
    sys.exit(1)
finally:
    db.close()
