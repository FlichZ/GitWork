# staffs/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Organization(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_prime_tech = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_prime_tech:
            Organization.objects.filter(is_prime_tech=True).exclude(id=self.id).update(is_prime_tech=False)
        super().save(*args, **kwargs)

        # Автоматическое создание чата для вторичной организации
        if not self.is_prime_tech and not hasattr(self, 'chat_with_prime_tech'):
            prime_tech = Organization.objects.filter(is_prime_tech=True).first()
            if prime_tech:
                Chat.objects.create(
                    prime_tech_organization=prime_tech,
                    secondary_organization=self
                )

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLES = (
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('staff', 'Staff'),
        ('external', 'External'),
    )
    role = models.CharField(max_length=20, choices=ROLES, default='staff')
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    can_add_user = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.role == 'admin':
            self.can_add_user = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.organization.name if self.organization else 'No Org'})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"Profile of {self.user.username}"


class Document(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('archived', 'Archived'),
    )

    document_name = models.CharField(max_length=255)
    document_description = models.TextField(blank=True, null=True)
    document_content = models.FileField(upload_to='documents/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sender = models.ForeignKey('UserProfile', on_delete=models.CASCADE, related_name='sent_documents')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_documents', blank=True, null=True)
    sender_organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='sent_documents')
    recipient_organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='received_documents', blank=True, null=True)
    recipient_name = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_sent = models.DateTimeField(blank=True, null=True)
    date_received = models.DateTimeField(blank=True, null=True)
    page_count = models.IntegerField(default=1)
    method = models.CharField(max_length=50, blank=True, null=True)
    attachment = models.CharField(max_length=255, blank=True, null=True)
    note = models.CharField(max_length=255, blank=True, null=True)
    status_change_log = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        # Автоматическое изменение статуса
        old_status = self.status if self.pk else None
        if self.date_sent and self.status == 'draft':
            self.status = 'sent'
        if self.date_received and self.status == 'sent':
            self.status = 'received'
        super().save(*args, **kwargs)

        # Логирование изменения статуса
        if old_status and old_status != self.status:
            self.add_status_change_log(self.sender.user, old_status, self.status)

    def add_status_change_log(self, user, old_status, new_status):
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {user.username} changed status from {old_status} to {new_status}\n"
        if self.status_change_log:
            self.status_change_log += log_entry
        else:
            self.status_change_log = log_entry
        self.save()

    def __str__(self):
        return self.document_name


class Index(models.Model):
    inverted_index = models.TextField(null=True, blank=True)

    def __str__(self):
        return "Document Index"


def post_user_created_signal(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


post_save.connect(post_user_created_signal, sender=User)


class UserActionLog(models.Model):
    ACTION_TYPES = (
        ('role_change', 'Role Change'),
        ('delete', 'Delete'),
        ('send_document', 'Send Document'),
        ('receive_document', 'Receive Document'),
        ('change_document_status', 'Change Document Status'),
        ('delete_document', 'Delete Document'),
        ('update_document_field', 'Update Document Field'),
        ('add_user', 'Add User'),
        ('view_document', 'View Document'),
        ('add_organization', 'Add Organization'),
        ('create_backup', 'Create Backup'),
        ('download_backup', 'Download Backup'),
        ('restore_backup', 'Restore Backup'),
        ('delete_backup', 'Delete Backup'),
    )

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='action_logs')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    details = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='performed_actions')

    def __str__(self):
        return f"{self.action_type} by {self.performed_by.username} on {self.user.username} at {self.timestamp}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.username}"


class Chat(models.Model):
    prime_tech_organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='prime_tech_chats')
    secondary_organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='secondary_chats', null=True, blank=True)
    is_support = models.BooleanField(default=False)
    name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.is_support:
            return f"Support Chat with {self.prime_tech_organization}"
        return f"Chat between {self.prime_tech_organization} and {self.secondary_organization or 'Guest'}"

    def save(self, *args, **kwargs):
        if not self.name:
            if self.is_support:
                self.name = f"Support Chat with {self.prime_tech_organization}"
            else:
                self.name = f"Chat with {self.secondary_organization or 'Guest'}"
        super().save(*args, **kwargs)

class ChatMessage(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages', null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        sender = self.sender.username if self.sender else f"Guest ({self.session_key})"
        return f"{sender}: {self.message} ({self.timestamp})"

# # Сигнал для автоматического создания чата при создании организации
# @receiver(post_save, sender=Organization)
# def create_organization_chat(sender, instance, created, **kwargs):
#     if created and not instance.is_prime_tech:
#         prime_tech_org = Organization.objects.filter(is_prime_tech=True).first()
#         if prime_tech_org:
#             Chat.objects.create(
#                 prime_tech_organization=prime_tech_org,
#                 secondary_organization=instance,
#                 name=f"Chat with {instance.name}"
#             )