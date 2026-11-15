"""Who may change accounts and permissions.

- teacher : no access to account management at all.
- admin   : runs sessions and may look after regular teacher accounts (add, rename, reset
            password, deactivate, delete, switch into) and their own name / password.
            An admin can NOT change anybody's role and can NOT touch another admin's account.
- owner   : one admin account. The only one that can make or unmake admins and manage
            other admins. The owner account itself can never be demoted, deactivated or deleted.
"""


def is_owner(te):
    return bool(te is not None and te.is_owner)


def can_manage(me, target):
    """May `me` rename / reset the password of / deactivate / delete `target`?"""
    if me is None or target is None or me.role != "admin":
        return False
    if is_owner(me) or target.id == me.id:
        return True
    return target.role != "admin" and not is_owner(target)


def can_switch_into(admin, target):
    """May this admin open `target`'s account without a password?"""
    if admin is None or target is None or admin.role != "admin" or not target.active:
        return False
    return is_owner(admin) or (target.role != "admin" and not is_owner(target))


def ensure_owner(db):
    """Keep exactly one owner: the account named "Admin" if it is an admin, else the oldest admin."""
    from .models import Teacher

    owners = db.query(Teacher).filter(Teacher.is_owner.is_(True)).order_by(Teacher.id).all()
    for extra in owners[1:]:
        extra.is_owner = False
    if owners:
        if owners[0].role != "admin":
            owners[0].role = "admin"
        return owners[0]
    admins = db.query(Teacher).filter_by(role="admin").order_by(Teacher.id).all()
    pick = next((a for a in admins if a.name == "Admin"), admins[0] if admins else None)
    if pick is not None:
        pick.is_owner = True
    return pick


# ---------- which sessions a person may see ----------

def visible_sessions(db, teacher):
    """Admins see every session. A teacher sees only the sessions in which a group is assigned to them."""
    from .models import AssessSession, Group

    if teacher is None:
        return []
    q = db.query(AssessSession)
    if teacher.role != "admin":
        mine = db.query(Group.session_id).filter(Group.teacher_id == teacher.id)
        q = q.filter(AssessSession.id.in_(mine))
    return q.order_by(AssessSession.date.desc(), AssessSession.id.desc()).all()


def can_open_session(db, teacher, session_id):
    from .models import Group

    if teacher is None:
        return False
    if teacher.role == "admin":
        return True
    return db.query(Group.id).filter(Group.session_id == session_id, Group.teacher_id == teacher.id).first() is not None
