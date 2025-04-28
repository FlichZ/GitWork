# staffs/urls.py
import tempfile
from django.urls import path
from django.views.static import serve
from .views import *
app_name = "staffs"

urlpatterns = [
    path("send/", send_document, name="send-document"),
    path("receive/", receive_document, name="receive-document"),
    path("dashboard/", dashboard, name="dashboard"),
    path("add-user/", add_user, name="add-user"),
    path("document/<int:document_id>/", document_detail, name="document-detail"),
    path("document/<int:document_id>/download-page/<int:page_index>/", download_page, name="download-page"),
    path("document-log/", document_log, name="document_log"),
    path("update-document-field/", update_document_field, name="update_document_field"),  # Новый URL для AJAX
    path('change-document-status/', change_document_status, name='change_document_status'),
    path('status-log-console/', status_log_console, name='status_log_console'),
    path('user-management/', user_management, name='user_management'),
    path('change-user-role/', change_user_role, name='change_user_role'),
    path('delete-user/', delete_user, name='delete_user'),
    path('user-action-log/', user_action_log, name='user_action_log'),
    path('notifications/', notifications, name='notifications'),
    path('delete-document/', delete_document, name='delete_document'),
    path('add-organization/', add_organization, name='add-organization'),  # Новый URL
    path('get-organization/', get_organization, name='get_organization'),
    path('edit-organization/', edit_organization, name='edit_organization'),
    path('delete-organization/', delete_organization, name='delete_organization'),
    path('get-org-users/', get_org_users, name='get_org_users'),
    path('get-chats/', get_chats, name='get_chats'),
    path('get-support-chat/', get_support_chat, name='get_support_chat'),
    path('chat-history/<int:chat_id>/', chat_history, name='chat_history'),
    path('support-chat-history/', support_chat_history, name='support_chat_history'),
    path('backup/', backup_management, name='backup_management'),
    path('backup/create/', create_backup, name='create_backup'),
    path('backup/download/<str:filename>/', download_backup, name='download_backup'),
    path('backup/restore/', restore_backup, name='restore_backup'),
    path('backup/delete/', delete_backup, name='delete_backup'),
]
