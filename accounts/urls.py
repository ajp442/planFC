from django.urls import path, re_path

from . import member_views, views

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("profile/picture/<int:user_id>/", views.profile_picture, name="profile_picture"),
    path("profile/delete/", views.delete_account, name="delete_account"),
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),
    path("push/test/", views.push_test, name="push_test"),
    # Admins only. docs/ADMIN_GUIDE.md walks through these pages.
    path("members/", member_views.member_list, name="member_list"),
    path("members/add/", member_views.member_add, name="member_add"),
    path("members/activity/", member_views.member_activity, name="member_activity"),
    path("members/<int:user_id>/", member_views.member_detail, name="member_detail"),
    path("members/<int:user_id>/role/", member_views.member_role, name="member_role"),
    path("members/<int:user_id>/delete/", member_views.member_delete, name="member_delete"),
    path("members/<int:user_id>/link/", member_views.member_link, name="member_link"),
    # Only the actions the view knows; anything else is a 404.
    re_path(
        rf"^members/(?P<user_id>\d+)/(?P<action>{'|'.join(member_views.MEMBER_ACTIONS)})/$",
        member_views.member_action,
        name="member_action",
    ),
    # Where an invitation email leads. Public: the link is the credential.
    path("invite/<str:uidb64>/<str:token>/", member_views.accept_invite, name="accept_invite"),
]
