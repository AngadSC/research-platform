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
    path(_P + "handover/", views.ProjectHandoverView.as_view(), name="project-handover"),
    path(
        "labs/<uuid:lab_id>/members/<uuid:membership_id>/handover/",
        views.MemberHandoverView.as_view(),
        name="member-handover",
    ),
    path("labs/<uuid:lab_id>/my-tasks/", views.MyTaskListView.as_view(), name="my-tasks"),
    path(_P + "tasks/", views.TaskListCreateView.as_view(), name="task-list"),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/",
        views.TaskDetailView.as_view(),
        name="task-detail",
    ),
    path(_P + "messages/", views.ChatMessageListCreateView.as_view(), name="chatmessage-list"),
    path(_P + "messages/read/", views.ChatReadView.as_view(), name="chatmessage-read"),
    path("labs/<uuid:lab_id>/chat/unread/", views.ChatUnreadView.as_view(), name="chat-unread"),
    path(
        "labs/<uuid:lab_id>/messages/<uuid:chatmessage_id>/",
        views.ChatMessageDetailView.as_view(),
        name="chatmessage-detail",
    ),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/posts/",
        views.TaskPostListCreateView.as_view(),
        name="taskpost-list",
    ),
    path(
        "labs/<uuid:lab_id>/task-posts/<uuid:taskpost_id>/",
        views.TaskPostDetailView.as_view(),
        name="taskpost-detail",
    ),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/documents/",
        views.TaskDocumentAddView.as_view(),
        name="task-document-add",
    ),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/documents/<uuid:document_id>/",
        views.TaskDocumentRemoveView.as_view(),
        name="task-document-remove",
    ),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/attachments/",
        views.TaskAttachmentAddView.as_view(),
        name="task-attachment-add",
    ),
    path(
        "labs/<uuid:lab_id>/tasks/<uuid:task_id>/attachments/<uuid:attachment_id>/",
        views.TaskAttachmentRemoveView.as_view(),
        name="task-attachment-remove",
    ),
]
