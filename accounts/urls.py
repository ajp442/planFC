from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("profile/picture/<int:user_id>/", views.profile_picture, name="profile_picture"),
    path("profile/delete/", views.delete_account, name="delete_account"),
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),
    path("push/test/", views.push_test, name="push_test"),
]
