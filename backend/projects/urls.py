from django.urls import path

from projects import views

app_name = "projects"
_P = "labs/<uuid:lab_id>/projects/<uuid:project_id>/"
urlpatterns = [
    path(
        "labs/<uuid:lab_id>/projects/", views.ProjectListCreateView.as_view(), name="project-list"
    ),
    path(_P, views.ProjectDetailView.as_view(), name="project-detail"),
    path(_P + "members/", views.ProjectMemberListCreateView.as_view(), name="projectmember-list"),
    path(
        "labs/<uuid:lab_id>/project-members/<uuid:projectmembership_id>/",
        views.ProjectMemberDetailView.as_view(),
        name="projectmember-detail",
    ),
    path(_P + "deadlines/", views.DeadlineListCreateView.as_view(), name="deadline-list"),
    path(
        "labs/<uuid:lab_id>/deadlines/<uuid:projectdeadline_id>/",
        views.DeadlineDetailView.as_view(),
        name="deadline-detail",
    ),
    path(
        "labs/<uuid:lab_id>/retention/due/",
        views.RetentionDueView.as_view(),
        name="retention-due",
    ),
    path(_P + "tasks/", views.TaskListCreateView.as_view(), name="task-list"),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/",
        views.TaskDetailView.as_view(),
        name="task-detail",
    ),
]
