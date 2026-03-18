from odoo import SUPERUSER_ID, api


def post_init_hook(env):
    """Give the built-in admin access to the app after a fresh install."""
    if not hasattr(env, "registry"):
        env = api.Environment(env, SUPERUSER_ID, {})
    admin_user = env.ref("base.user_admin", raise_if_not_found=False)
    manager_group = env.ref(
        "matomo_analytics.group_matomo_manager", raise_if_not_found=False
    )
    if admin_user and manager_group and manager_group not in admin_user.groups_id:
        admin_user.write({"groups_id": [(4, manager_group.id)]})
