# staffs/urls.py
import tempfile
from django.urls import path
from django.views.static import serve
from .views import send_document, receive_document, dashboard, add_user, document_detail, download_page, document_log, \
    update_document_field, change_document_status, status_log_console, user_action_log, user_management, \
    change_user_role, delete_user, notifications, delete_document, add_organization

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

]