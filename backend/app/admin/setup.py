from __future__ import annotations

from sqladmin import Admin, ModelView

from ..db.session import get_engine
from ..models.user import User


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.full_name]


def mount_admin(app):
    admin = Admin(app=app, engine=get_engine(), title="Tokenlysis Admin")
    admin.add_view(UserAdmin)
    return admin
