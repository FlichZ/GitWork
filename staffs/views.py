import csv
import sqlite3
from datetime import datetime
import json

from django.conf import settings
from django.db import connections
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from .models import Document, Organization, User, UserActionLog, Notification, ChatMessage, Chat
from .forms import SendDocumentForm, CustomUserCreationForm, OrganizationCreationForm, OrganizationEditForm
from django.contrib import messages as django_messages
from django.http import FileResponse, HttpResponse, JsonResponse
import os
from mimetypes import guess_type
import io
import base64
from pdf2image import convert_from_path
from docx import Document as DocxDocument
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import tempfile
import shutil
import logging
import subprocess
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from io import BytesIO
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


# Настройка логирования
logger = logging.getLogger(__name__)

@login_required
def document_detail(request, document_id):
    document = get_object_or_404(Document, id=document_id)
    user = request.user
    organization = user.organization

    # Проверка доступа
    has_access = False
    if organization.is_prime_tech:
        has_access = (
            document.sender_organization == organization or
            document.recipient_organization == organization
        )
    else:
        has_access = (
            (document.sender == user.userprofile or document.recipient == user) and
            (document.sender_organization == organization or document.recipient_organization == organization)
        )

    if not has_access:
        django_messages.error(request, ("You do not have permission to view this document."))
        return redirect('staffs:dashboard')

    # Логирование просмотра документа
    UserActionLog.objects.create(
        user=user,
        action_type='view_document',
        details=f"Viewed document '{document.document_name}' (ID: {document.id})",
        performed_by=user
    )

    # Установка date_received, если пользователь — получатель и дата ещё не установлена
    if user == document.recipient and not document.date_received:
        document.date_received = timezone.now()
        document.save()

    page_images_base64 = []
    if document.document_content:
        file_path = document.document_content.path
        logger.info(f"Processing file: {file_path}")

        if not os.path.exists(file_path):
            logger.error(f"File not found on server: {file_path}")
            django_messages.error(request, ("File not found on server: ") + file_path)
            page_images_base64 = None
        else:
            content_type, _ = guess_type(file_path)
            logger.info(f"Detected content type: {content_type}")

            try:
                if content_type == 'application/pdf':
                    images = convert_from_path(file_path, dpi=200)
                    for img in images:
                        buffered = io.BytesIO()
                        img.save(buffered, format="PNG")
                        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                        page_images_base64.append(img_base64)
                elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    doc = DocxDocument(file_path)
                    text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
                    if not text:
                        logger.warning(f"DOCX file is empty: {file_path}")
                        django_messages.warning(request, ("The DOCX file is empty or contains no readable text."))
                    else:
                        images = text_to_images(text, width=800, height=1200)
                        for img in images:
                            buffered = io.BytesIO()
                            img.save(buffered, format="PNG")
                            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                            page_images_base64.append(img_base64)
                elif content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                    df = pd.read_excel(file_path)
                    text = df.to_string(index=False)
                    images = text_to_images(text, width=800, height=1200)
                    for img in images:
                        buffered = io.BytesIO()
                        img.save(buffered, format="PNG")
                        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                        page_images_base64.append(img_base64)
                elif content_type == 'text/plain':
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    images = text_to_images(text, width=800, height=1200)
                    for img in images:
                        buffered = io.BytesIO()
                        img.save(buffered, format="PNG")
                        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                        page_images_base64.append(img_base64)
                else:
                    logger.warning(f"Unsupported file type: {content_type} for file {file_path}")
                    django_messages.warning(request, _("Preview not available for this file type."))
                    page_images_base64 = None
            except Exception as e:
                logger.error(f"Error generating preview for {file_path}: {str(e)}", exc_info=True)
                page_images_base64 = None
                django_messages.error(request, _("Error generating preview: ") + str(e))
    else:
        logger.warning(f"No file attached to document ID {document_id}")
        django_messages.warning(request, ("No file attached to this document."))
        page_images_base64 = None

    if page_images_base64:
        page_data = [{'base64': img, 'download_url': f'/staffs/document/{document_id}/download-page/{i}/'} for i, img in enumerate(page_images_base64)]
    else:
        page_data = None

    context = {
        'document': document,
        'page_data': page_data,
        'is_prime_tech': organization.is_prime_tech,
        'status_choices': Document.STATUS_CHOICES,
    }
    return render(request, 'staffs/document_detail.html', context)

@login_required
def download_page(request, document_id, page_index):
    document = get_object_or_404(Document, id=document_id)
    user = request.user
    organization = user.organization

    has_access = False
    if organization.is_prime_tech:
        has_access = (
            document.sender_organization == organization or
            document.recipient_organization == organization
        )
    else:
        has_access = (
            (document.sender == user.userprofile or document.recipient == user) and
            (document.sender_organization == organization or document.recipient_organization == organization)
        )

    if not has_access:
        django_messages.error(request, ("You do not have permission to download this page."))
        return redirect('staffs:document-detail', document_id=document_id)

    file_path = document.document_content.path
    content_type, _ = guess_type(file_path)
    page_images = []

    try:
        if content_type == 'application/pdf':
            images = convert_from_path(file_path, dpi=200)
            page_images = images
        elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            doc = DocxDocument(file_path)
            text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            images = text_to_images(text, width=800, height=1200)
            page_images = images
        elif content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            df = pd.read_excel(file_path)
            text = df.to_string(index=False)
            images = text_to_images(text, width=800, height=1200)
            page_images = images
        elif content_type == 'text/plain':
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            images = text_to_images(text, width=800, height=1200)
            page_images = images

        if page_index < len(page_images):
            buffered = io.BytesIO()
            page_images[page_index].save(buffered, format="PNG")
            buffered.seek(0)
            return FileResponse(buffered, as_attachment=True, filename=f'page_{page_index}.png')
        else:
            django_messages.error(request, _("Page not found."))
            return redirect('staffs:document-detail', document_id=document_id)
    except Exception as e:
        django_messages.error(request, _("Error generating page for download: ") + str(e))
        return redirect('staffs:document-detail', document_id=document_id)


def text_to_images(text, width=800, height=1200):
    images = []
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except:
        font = ImageFont.load_default()

    lines = []
    current_line = ""
    for word in text.split():
        test_line = current_line + " " + word if current_line else word
        if ImageDraw.Draw(Image.new('RGB', (1, 1))).textlength(test_line, font=font) < (width - 40):
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    current_page_lines = []
    y = 20
    for line in lines:
        if y + 20 > height - 20:
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            y_pos = 20
            for page_line in current_page_lines:
                draw.text((20, y_pos), page_line, font=font, fill='black')
                y_pos += 20
            images.append(img)
            current_page_lines = []
            y = 20
        current_page_lines.append(line)
        y += 20

    if current_page_lines:
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        y_pos = 20
        for page_line in current_page_lines:
            draw.text((20, y_pos), page_line, font=font, fill='black')
            y_pos += 20
        images.append(img)

    return images if images else [Image.new('RGB', (width, height), color='white')]


@login_required
def dashboard(request):
    user = request.user

    # Получаем активную вкладку из GET-параметра (по умолчанию 'sent')
    active_tab = request.GET.get('tab', 'sent')

    # Получаем отправленные и полученные документы
    sent_documents = Document.objects.filter(sender__user=user)
    received_documents = Document.objects.filter(recipient=user)

    # Статистика
    stats = {
        'total_sent': sent_documents.count(),
        'total_received': received_documents.count(),
        'total_draft': sent_documents.filter(status='draft').count() + received_documents.filter(status='draft').count(),
        'total_archived': sent_documents.filter(status='archived').count() + received_documents.filter(status='archived').count(),
        'total_documents': sent_documents.count() + received_documents.count(),
        'sent_status': sent_documents.filter(status='sent').count() + received_documents.filter(status='sent').count(),
        'received_status': sent_documents.filter(status='received').count() + received_documents.filter(status='received').count(),
    }

    # Фильтры
    status_filter = request.GET.get('status', '')
    start_date = request.GET.get('start_date', None)
    end_date = request.GET.get('end_date', None)
    org_filter = request.GET.get('org', '')
    sort_by = request.GET.get('sort_by', 'date_created')
    sort_order = request.GET.get('sort_order', 'desc')

    # Инициализация документов для активной вкладки
    documents = None
    page_obj = None

    if active_tab == 'sent':
        documents = sent_documents
    else:  # active_tab == 'received'
        documents = received_documents

    # Применяем фильтры
    if status_filter:
        documents = documents.filter(status=status_filter)
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            documents = documents.filter(date_created__gte=start_date)
        except ValueError:
            django_messages.error(request, _("Invalid start date format. Use YYYY-MM-DD."))
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            documents = documents.filter(date_created__lte=end_date)
        except ValueError:
            django_messages.error(request, _("Invalid end date format. Use YYYY-MM-DD."))
    if org_filter:
        documents = documents.filter(Q(sender_organization__id=org_filter) | Q(recipient_organization__id=org_filter))

    # Сортировка
    if sort_by == 'status':
        sort_field = 'status'
    else:
        sort_field = 'date_created'
    if sort_order == 'asc':
        documents = documents.order_by(sort_field)
    else:
        documents = documents.order_by(f'-{sort_field}')

    # Пагинация
    paginator = Paginator(documents, 9)  # 9 документов на страницу (3 ряда по 3 карточки)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Получаем список организаций для фильтра
    organizations = Organization.objects.all()

    # Список статусов для фильтра
    status_choices = Document.STATUS_CHOICES

    context = {
        'stats': stats,
        'documents': page_obj,
        'page_obj': page_obj,
        'status_choices': status_choices,
        'current_status': status_filter,
        'current_start_date': start_date,
        'current_end_date': end_date,
        'organizations': organizations,
        'current_org': org_filter,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'active_tab': active_tab,
    }
    return render(request, 'staffs/dashboard.html', context)


@login_required
def send_document(request):
    if request.method == 'POST':
        form = SendDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.sender = request.user.userprofile
            document.sender_organization = request.user.organization
            document.status = 'sent'
            document.date_sent = timezone.now()
            document.save()

            # Логирование действия отправки документа
            UserActionLog.objects.create(
                user=request.user,
                action_type='send_document',
                details=f"Sent document '{document.document_name}' to {document.recipient.username}",
                performed_by=request.user
            )

            # Создаём уведомление для получателя
            if document.recipient:
                Notification.objects.create(
                    user=document.recipient,
                    message=f"New document '{document.document_name}' received from {document.sender.user.username}"
                )

            django_messages.success(request, _("Document sent successfully."))
            return redirect('staffs:dashboard')
    else:
        form = SendDocumentForm()
    return render(request, 'staffs/send.html', {'form': form})


def landing_page(request):
    return render(request, 'landing_page.html')


def send_or_receive_view(request):
    return render(request, 'send_or_receive.html')


@login_required
def receive_document(request):
    documents = Document.objects.filter(recipient=request.user)
    updated = False
    for doc in documents:
        if doc.status == 'sent' and not doc.date_received:
            doc.status = 'received'
            doc.date_received = timezone.now()
            doc.save()
            updated = True

            # Логирование действия получения документа
            UserActionLog.objects.create(
                user=request.user,
                action_type='receive_document',
                details=f"Received document '{doc.document_name}' from {doc.sender.user.username}",
                performed_by=request.user
            )

    if updated:
        django_messages.success(request, _("Some documents have been marked as received."))

    # Фильтрация по статусу
    status_filter = request.GET.get('status', '')
    if status_filter:
        documents = documents.filter(status=status_filter)

    # Пагинация
    paginator = Paginator(documents, 6)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'documents': page_obj,
        'status_choices': Document.STATUS_CHOICES,
        'current_status': status_filter,
        'page_obj': page_obj,
    }
    return render(request, 'staffs/receive.html', context)


@login_required
def add_user(request):
    if request.user.role != 'admin':
        django_messages.error(request, _("You do not have permission to add users."))
        return redirect('staffs:dashboard')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            # Логирование добавления пользователя
            UserActionLog.objects.create(
                user=user,
                action_type='add_user',
                details=f"Added new user '{user.username}' with role '{user.role}' in organization '{user.organization.name}'",
                performed_by=request.user
            )

            django_messages.success(request, _("User added successfully!"))
            return redirect('staffs:dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'staffs/add_user.html', {'form': form})


@login_required
def document_log(request):
    user = request.user
    organization = user.organization

    if not organization.is_prime_tech:
        django_messages.error(request, _("Only PrimeTech organizations can access this page."))
        return redirect('staffs:dashboard')

    # Обработка скачивания таблицы
    if 'download' in request.GET:
        documents = Document.objects.filter(
            Q(sender_organization=organization) | Q(recipient_organization=organization)
        ).order_by('date_sent')

        data = []
        for idx, doc in enumerate(documents, start=1):
            data.append({
                'Исходящий номер': idx,
                'Дата исходящего номера и дату принятия': doc.date_sent.strftime('%d.%m.%Y') if doc.date_sent else '-',
                'Адресат': doc.recipient_organization.name if doc.recipient_organization else (doc.recipient_name or '-'),
                'Краткое содержание': doc.summary or '-',
                'Количество страниц': doc.page_count,
                'Пирожки': doc.attachment or '-',
                'Исполнитель': doc.sender.user.username if doc.sender else '-',
                'Способ отправки': doc.method or 'e-mail',
                'Дата отправки': doc.date_sent.strftime('%d.%m.%Y') if doc.date_sent else '-',
                'Дата исполнения': doc.date_received.strftime('%d.%m.%Y') if doc.date_received else '-',
                'Отметка о выполнении в поле': doc.note or '01-19',
            })

        df = pd.DataFrame(data)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Document Log', index=False)

        workbook = openpyxl.load_workbook(output)
        worksheet = workbook['Document Log']

        for col in worksheet.columns:
            column_letter = col[0].column_letter
            worksheet[f'{column_letter}1'].font = Font(bold=True)
            worksheet[f'{column_letter}1'].alignment = Alignment(horizontal='center', vertical='center')
            worksheet.column_dimensions[column_letter].width = 20

        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        for row in worksheet.rows:
            for cell in row:
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center', vertical='center')

        output.seek(0)
        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="document_log.xlsx"'
        return response

    # Формирование данных для отображения таблицы
    documents = Document.objects.filter(
        Q(sender_organization=organization) | Q(recipient_organization=organization)
    ).order_by('date_sent')

    table_data = []
    for idx, doc in enumerate(documents, start=1):
        table_data.append({
            'id': doc.id,
            'number': idx,
            'date_sent_accepted': doc.date_sent.strftime('%d.%m.%Y') if doc.date_sent else '-',
            'recipient': doc.recipient_organization.name if doc.recipient_organization else (doc.recipient_name or '-'),
            'summary': doc.summary or '-',
            'page_count': doc.page_count,
            'attachment': doc.attachment or '-',
            'sender': doc.sender.user.username if doc.sender else '-',
            'method': doc.method or 'e-mail',
            'date_sent': doc.date_sent.strftime('%d.%m.%Y') if doc.date_sent else '-',
            'date_received': doc.date_received.strftime('%d.%m.%Y') if doc.date_received else '-',
            'note': doc.note or '01-19',
        })

    context = {
        'table_data': table_data,
    }
    return render(request, 'staffs/document_log.html', context)


@require_POST
@login_required
def update_document_field(request):
    document_id = request.POST.get('document_id')
    field = request.POST.get('field')
    value = request.POST.get('value')

    try:
        document = Document.objects.get(id=document_id)
        user = request.user
        organization = user.organization

        if not organization.is_prime_tech:
            return JsonResponse({'status': 'error', 'message': _("Only PrimeTech organizations can edit this table.")}, status=403)

        # Валидация и обновление поля
        if field == 'date_sent_accepted' or field == 'date_sent' or field == 'date_received':
            if value == '-':
                if field == 'date_sent_accepted' or field == 'date_sent':
                    document.date_sent = None
                elif field == 'date_received':
                    document.date_received = None
            else:
                try:
                    date_value = datetime.strptime(value, '%d.%m.%Y')
                    if field == 'date_sent_accepted' or field == 'date_sent':
                        document.date_sent = date_value
                    elif field == 'date_received':
                        document.date_received = date_value
                except ValueError:
                    return JsonResponse({'status': 'error', 'message': _("Invalid date format. Use DD.MM.YYYY.")}, status=400)
        elif field == 'page_count':
            try:
                page_count = int(value)
                if page_count < 1:
                    return JsonResponse({'status': 'error', 'message': _("Page count must be a positive integer.")}, status=400)
                document.page_count = page_count
            except ValueError:
                return JsonResponse({'status': 'error', 'message': _("Page count must be a number.")}, status=400)
        elif field == 'summary':
            document.summary = value
        elif field == 'method':
            document.method = value
        elif field == 'recipient_name':
            document.recipient_name = value
        elif field == 'attachment':
            document.attachment = value
        elif field == 'note':
            document.note = value

        document.save()
        return JsonResponse({'status': 'success', 'message': _("Field updated successfully.")})

    except Document.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Document not found.")}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def change_document_status(request):
    if not request.user.organization.is_prime_tech:
        return JsonResponse({'status': 'error', 'message': _("Only PrimeTech organizations can change document status.")}, status=403)

    document_id = request.POST.get('document_id')
    new_status = request.POST.get('status')

    try:
        document = Document.objects.get(id=document_id)
        old_status = document.status
        if new_status in dict(Document.STATUS_CHOICES):
            document.status = new_status
            document.add_status_change_log(request.user, old_status, new_status)
            document.save()
            return JsonResponse({'status': 'success', 'message': _("Status updated successfully.")})
        return JsonResponse({'status': 'error', 'message': _("Invalid status.")}, status=400)
    except Document.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Document not found.")}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def status_log_console(request):
    user = request.user
    organization = user.organization

    if not organization.is_prime_tech:
        django_messages.error(request, _("Only PrimeTech organizations can access this page."))
        return redirect('staffs:dashboard')

    # Проверка на запрос экспорта
    if 'export' in request.GET and request.GET['export'] == 'csv':
        documents = Document.objects.filter(
            Q(sender_organization=organization) | Q(recipient_organization=organization)
        )
        log_entries = []
        for doc in documents:
            if doc.status_change_log:
                entries = doc.status_change_log.strip().split('\n')
                for entry in entries:
                    if entry:
                        try:
                            timestamp_str, rest = entry.split(' - ', 1)
                            username, action = rest.split(' changed status from ', 1)
                            old_status, new_status = action.split(' to ')
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            log_entries.append({
                                'document': doc,
                                'timestamp': timestamp,
                                'username': username,
                                'old_status': old_status,
                                'new_status': new_status,
                            })
                        except (ValueError, IndexError):
                            continue

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="status_change_logs.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Document Name', 'User', 'Old Status', 'New Status'])
        for entry in log_entries:
            writer.writerow([
                entry['timestamp'],
                entry['document'].document_name,
                entry['username'],
                entry['old_status'],
                entry['new_status'],
            ])
        return response

    documents = Document.objects.filter(
        Q(sender_organization=organization) | Q(recipient_organization=organization)
    )

    start_date = request.GET.get('start_date', None)
    end_date = request.GET.get('end_date', None)
    user_filter = request.GET.get('user', None)
    document_filter = request.GET.get('document', None)

    log_entries = []
    for doc in documents:
        if doc.status_change_log:
            entries = doc.status_change_log.strip().split('\n')
            for entry in entries:
                if entry:
                    try:
                        timestamp_str, rest = entry.split(' - ', 1)
                        username, action = rest.split(' changed status from ', 1)
                        old_status, new_status = action.split(' to ')
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        log_entries.append({
                            'document': doc,
                            'timestamp': timestamp,
                            'username': username,
                            'old_status': old_status,
                            'new_status': new_status,
                        })
                    except (ValueError, IndexError):
                        continue

    # Фильтр по диапазону дат
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            log_entries = [
                entry for entry in log_entries
                if entry['timestamp'].date() >= start_date.date()
            ]
        except ValueError:
            django_messages.error(request, _("Invalid start date format. Use YYYY-MM-DD."))

    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            log_entries = [
                entry for entry in log_entries
                if entry['timestamp'].date() <= end_date.date()
            ]
        except ValueError:
            django_messages.error(request, _("Invalid end date format. Use YYYY-MM-DD."))

    if user_filter:
        log_entries = [
            entry for entry in log_entries
            if user_filter.lower() in entry['username'].lower()
        ]

    if document_filter:
        log_entries = [
            entry for entry in log_entries
            if document_filter.lower() in entry['document'].document_name.lower()
        ]

    log_entries.sort(key=lambda x: x['timestamp'], reverse=True)

    paginator = Paginator(log_entries, 10)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'log_entries': page_obj,
        'page_obj': page_obj,
        'current_start_date': start_date,
        'current_end_date': end_date,
        'current_user': user_filter,
        'current_document': document_filter,
    }
    return render(request, 'staffs/status_log_console.html', context)


@login_required
def user_management(request):
    user = request.user

    if user.role != 'admin':
        django_messages.error(request, _("Only admins can access this page."))
        return redirect('staffs:dashboard')

    # Определяем активную вкладку
    active_tab = request.GET.get('tab', 'users')

    users = User.objects.all()
    organizations = Organization.objects.all()

    org_filter = request.GET.get('org', None)
    role_filter = request.GET.get('role', None)

    if org_filter:
        users = users.filter(organization__id=org_filter)

    if role_filter:
        users = users.filter(role=role_filter)

    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Статистика
    stats = {
        'total_users': User.objects.count(),
        'admins': User.objects.filter(role='admin').count(),
        'managers': User.objects.filter(role='manager').count(),
        'staff': User.objects.filter(role='staff').count(),
        'external': User.objects.filter(role='external').count(),
    }

    role_choices = User.ROLES

    context = {
        'users': page_obj,
        'page_obj': page_obj,
        'organizations': organizations,
        'role_choices': role_choices,
        'current_org': org_filter,
        'current_role': role_filter,
        'stats': stats,
        'active_tab': active_tab,
    }
    return render(request, 'staffs/user_management.html', context)


@require_POST
@login_required
def change_user_role(request):
    user = request.user
    if user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can change user roles.")}, status=403)

    user_id = request.POST.get('user_id')
    new_role = request.POST.get('role')

    try:
        target_user = User.objects.get(id=user_id)
        if new_role in dict(User.ROLES):
            old_role = target_user.role
            target_user.role = new_role
            target_user.save()
            # Логирование
            UserActionLog.objects.create(
                user=target_user,
                action_type='role_change',
                details=f"Role changed from {old_role} to {new_role}",
                performed_by=user
            )
            return JsonResponse({'status': 'success', 'message': _("User role updated successfully.")})
        return JsonResponse({'status': 'error', 'message': _("Invalid role.")}, status=400)
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("User not found.")}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def delete_user(request):
    user = request.user
    if user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can delete users.")}, status=403)

    user_id = request.POST.get('user_id')

    try:
        target_user = User.objects.get(id=user_id)
        if target_user == user:
            return JsonResponse({'status': 'error', 'message': _("You cannot delete yourself.")}, status=400)
        # Логирование перед удалением
        UserActionLog.objects.create(
            user=target_user,
            action_type='delete',
            details="User deleted",
            performed_by=user
        )
        target_user.delete()
        return JsonResponse({'status': 'success', 'message': _("User deleted successfully.")})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("User not found.")}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def user_action_log(request):
    user = request.user

    if user.role != 'admin':
        django_messages.error(request, _("Only admins can access this page."))
        return redirect('staffs:dashboard')

    logs = UserActionLog.objects.all().order_by('-timestamp')

    # Фильтры
    user_filter = request.GET.get('user', None)
    action_filter = request.GET.get('action', None)

    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)

    if action_filter:
        logs = logs.filter(action_type=action_filter)

    # Пагинация
    paginator = Paginator(logs, 10)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'logs': page_obj,
        'page_obj': page_obj,
        'action_choices': UserActionLog.ACTION_TYPES,
        'current_user': user_filter,
        'current_action': action_filter,
    }
    return render(request, 'staffs/user_action_log.html', context)


@login_required
def notifications(request):
    notifications = request.user.notifications.all().order_by('-created_at')
    if request.method == 'POST' and 'mark_as_read' in request.POST:
        notification_id = request.POST.get('notification_id')
        notification = notifications.filter(id=notification_id).first()
        if notification:
            notification.is_read = True
            notification.save()
            return JsonResponse({'status': 'success', 'message': _("Notification marked as read.")})
        return JsonResponse({'status': 'error', 'message': _("Notification not found.")}, status=404)

    # Пагинация
    paginator = Paginator(notifications, 10)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'notifications': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'staffs/notifications.html', context)


def is_prime_tech(user):
    return user.organization.is_prime_tech if user.is_authenticated and user.organization else False


@login_required
@user_passes_test(is_prime_tech)
def delete_document(request):
    if request.method == 'POST':
        document_id = request.POST.get('document_id')
        try:
            document = get_object_or_404(Document, id=document_id)

            # Проверка, что пользователь имеет доступ к этому документу (например, он из PrimeTech)
            if not request.user.organization.is_prime_tech:
                return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

            # Логирование действия удаления
            UserActionLog.objects.create(
                user=request.user,
                action_type='delete_document',
                details=f"Deleted document '{document.document_name}' (ID: {document.id})",
                performed_by=request.user
            )

            # Удаление файла с диска, если он существует
            if document.document_content and os.path.isfile(document.document_content.path):
                os.remove(document.document_content.path)

            # Удаление записи документа из базы данных
            document.delete()

            return JsonResponse({'status': 'success', 'message': 'Document deleted successfully'})
        except Document.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Document not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@login_required
def add_organization(request):
    if request.user.role != 'admin':
        django_messages.error(request, _("You do not have permission to add organizations."))
        return redirect('staffs:dashboard')

    if request.method == 'POST':
        form = OrganizationCreationForm(request.POST)
        if form.is_valid():
            organization = form.save()

            # Логирование добавления организации
            UserActionLog.objects.create(
                user=request.user,
                action_type='add_organization',
                details=f"Added new organization '{organization.name}'",
                performed_by=request.user
            )

            django_messages.success(request, _("Organization added successfully!"))
            return redirect('staffs:user_management', tab='organizations')
    else:
        form = OrganizationCreationForm()

    return render(request, 'staffs/add_organization.html', {'form': form})


@require_GET
@login_required
def get_organization(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can access this data.")}, status=403)

    org_id = request.GET.get('org_id')
    try:
        organization = Organization.objects.get(id=org_id)
        return JsonResponse({
            'status': 'success',
            'organization': {
                'id': organization.id,
                'name': organization.name,
                'is_prime_tech': organization.is_prime_tech,
            }
        })
    except Organization.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Organization not found.")}, status=404)


@require_POST
@login_required
def edit_organization(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can edit organizations.")}, status=403)

    org_id = request.POST.get('org_id')
    try:
        organization = Organization.objects.get(id=org_id)
        form = OrganizationEditForm(request.POST, instance=organization)
        if form.is_valid():
            form.save()
            UserActionLog.objects.create(
                user=request.user,
                action_type='edit_organization',
                details=f"Edited organization '{organization.name}'",
                performed_by=request.user
            )
            return JsonResponse({'status': 'success', 'message': _("Organization updated successfully.")})
        else:
            errors = form.errors.as_json()
            return JsonResponse({'status': 'error', 'message': json.loads(errors)}, status=400)
    except Organization.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Organization not found.")}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def delete_organization(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can delete organizations.")}, status=403)

    org_id = request.POST.get('org_id')
    try:
        organization = Organization.objects.get(id=org_id)
        if organization.users.exists():
            return JsonResponse({'status': 'error', 'message': _("Cannot delete organization with associated users.")}, status=400)
        if organization.is_prime_tech:
            return JsonResponse({'status': 'error', 'message': _("Cannot delete PrimeTech organization.")}, status=400)
        # Логирование перед удалением
        UserActionLog.objects.create(
            user=request.user,
            action_type='delete_organization',
            details=f"Deleted organization '{organization.name}'",
            performed_by=request.user
        )
        organization.delete()
        return JsonResponse({'status': 'success', 'message': _("Organization deleted successfully.")})
    except Organization.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Organization not found.")}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_GET
@login_required
def get_org_users(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can access this data.")}, status=403)

    org_id = request.GET.get('org_id')
    try:
        organization = Organization.objects.get(id=org_id)
        users = organization.users.all()
        users_data = [{
            'id': user.id,
            'username': user.username,
            'role': dict(User.ROLES).get(user.role, user.role),
        } for user in users]
        return JsonResponse({
            'status': 'success',
            'users': users_data
        })
    except Organization.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Organization not found.")}, status=404)


@login_required
def get_chats(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'User not authenticated'}, status=401)

    user_org = request.user.organization
    if user_org.is_prime_tech:

        chats = Chat.objects.filter(prime_tech_organization=user_org, is_support=False)
    else:
        chats = Chat.objects.filter(secondary_organization=user_org, is_support=False)

    chat_list = [{
        'id': chat.id,
        'name': chat.secondary_organization.name if chat.secondary_organization else chat.name,
        'last_message': chat.messages.last().message if chat.messages.exists() else 'No messages'
    } for chat in chats]
    return JsonResponse({'status': 'success', 'chats': chat_list})


@require_GET
def get_support_chat(request):
    try:
        chat = Chat.objects.get(is_support=True)
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key
        return JsonResponse({
            'status': 'success',
            'chat': {
                'id': chat.id,
                'name': chat.name,
                'last_message': chat.messages.last().message if chat.messages.exists() else None
            }
        })
    except Chat.DoesNotExist:
        prime_tech_org = Organization.objects.filter(is_prime_tech=True).first()
        if prime_tech_org:
            chat = Chat.objects.create(
                prime_tech_organization=prime_tech_org,
                is_support=True,
                name="Support Chat"
            )
            return JsonResponse({
                'status': 'success',
                'chat': {
                    'id': chat.id,
                    'name': chat.name,
                    'last_message': None
                }
            })
        return JsonResponse({'status': 'error', 'message': _("Support chat not found.")}, status=404)


@login_required
def chat_history(request, chat_id):
    user = request.user
    organization = user.organization

    try:
        chat = Chat.objects.get(id=chat_id, is_support=False)
        if not organization:
            return JsonResponse({'status': 'error', 'message': _("User has no organization.")}, status=403)
        if organization.is_prime_tech:
            if chat.prime_tech_organization != organization:
                return JsonResponse({'status': 'error', 'message': _("You do not have access to this chat.")}, status=403)
        else:
            if chat.secondary_organization != organization:
                return JsonResponse({'status': 'error', 'message': _("You do not have access to this chat.")}, status=403)

        messages = chat.messages.all()
        messages_data = [{
            'sender': msg.sender.username if msg.sender else "Guest",
            'message': msg.message,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for msg in messages]

        return JsonResponse({'status': 'success', 'messages': messages_data})

    except Chat.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Chat not found.")}, status=404)


@require_GET
def support_chat_history(request):
    try:
        chat = Chat.objects.get(is_support=True)
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key

        if request.user.is_authenticated and request.user.organization.is_prime_tech:
            messages = chat.messages.all()
        else:
            messages = chat.messages.filter(session_key=session_key) | chat.messages.filter(sender__organization__is_prime_tech=True)

        messages_data = [{
            'sender': msg.sender.username if msg.sender else "Guest",
            'message': msg.message,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for msg in messages.order_by('timestamp')]

        return JsonResponse({
            'status': 'success',
            'messages': messages_data
        })
    except Chat.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': _("Support chat not found.")}, status=404)



@login_required
def backup_management(request):
    if request.user.role != 'admin':
        django_messages.error(request, _("Only admins can access this page."))
        return redirect('staffs:dashboard')

    # Путь к папке для резервных копий
    backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    # Получаем список резервных копий
    backups = []
    for filename in os.listdir(backup_dir):
        file_path = os.path.join(backup_dir, filename)
        if os.path.isfile(file_path) and filename.endswith('.sql'):
            created_at = datetime.fromtimestamp(os.path.getctime(file_path))
            size = os.path.getsize(file_path) / (1024 * 1024)  # Размер в MB
            backups.append({
                'filename': filename,
                'created_at': created_at,
                'size': size,
            })

    # Сортировка по дате создания (от новых к старым)
    backups.sort(key=lambda x: x['created_at'], reverse=True)

    # Статистика
    stats = {
        'total_backups': len(backups),
        'last_backup': backups[0]['created_at'].strftime('%Y-%m-%d %H:%M:%S') if backups else None,
        'storage_used': sum(b['size'] for b in backups),
    }

    # Пагинация
    paginator = Paginator(backups, 9)  # 9 резервных копий на страницу
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'backups': page_obj,
        'page_obj': page_obj,
        'stats': stats,
    }
    return render(request, 'staffs/backup.html', context)

@login_required
def create_backup(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can create backups.")}, status=403)
    if request.method == 'POST':
        try:
            db_path = settings.DATABASES['default']['NAME']
            print(f"Database path: {db_path}")  # Отладка
            if not os.path.exists(db_path):
                return JsonResponse({'status': 'error', 'message': _("Database file not found.")}, status=404)
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            print(f"Backup dir: {backup_dir}")  # Отладка
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{timestamp}.sql"
            backup_path = os.path.join(backup_dir, backup_filename)
            print(f"Creating SQL backup: {backup_path}")  # Отладка
            with open(backup_path, 'w', encoding='utf-8') as f:
                process = subprocess.run(['sqlite3', db_path, '.dump'], stdout=subprocess.PIPE, text=True, check=True)
                f.write(process.stdout)
            print(f"Backup created successfully: {backup_filename}")  # Отладка
            UserActionLog.objects.create(
                user=request.user,
                action_type='create_backup',
                details=f"Created SQL backup '{backup_filename}'",
                performed_by=request.user
            )
            return JsonResponse({'status': 'success', 'message': _("Backup created successfully.")})
        except subprocess.CalledProcessError as e:
            print(f"Subprocess error: {str(e)}")  # Отладка
            return JsonResponse({'status': 'error', 'message': f"Failed to create SQL dump: {str(e)}"}, status=500)
        except Exception as e:
            print(f"General error: {str(e)}")  # Отладка
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': _("Invalid request method.")}, status=400)

@login_required
def download_backup(request, filename):
    if request.user.role != 'admin':
        django_messages.error(request, _("Only admins can download backups."))
        return redirect('staffs:dashboard')

    backup_path = os.path.join(settings.MEDIA_ROOT, 'backups', filename)
    if not os.path.exists(backup_path):
        django_messages.error(request, _("Backup file not found."))
        return redirect('staffs:backup_management')

    # Логирование
    UserActionLog.objects.create(
        user=request.user,
        action_type='download_backup',
        details=f"Downloaded SQL backup '{filename}'",
        performed_by=request.user
    )

    response = FileResponse(open(backup_path, 'rb'), as_attachment=True, filename=filename)
    response['Content-Type'] = 'application/sql'
    return response

@login_required
def restore_backup(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can restore backups.")}, status=403)

    if request.method == 'POST':
        filename = request.POST.get('filename')
        if not filename:
            return JsonResponse({'status': 'error', 'message': _("No backup filename provided.")}, status=400)

        try:
            # Путь к файлу резервной копии
            backup_path = os.path.join(settings.MEDIA_ROOT, 'backups', filename)
            print(f"Restoring from backup: {backup_path}")  # Отладка
            if not os.path.exists(backup_path):
                return JsonResponse({'status': 'error', 'message': _("Backup file not found.")}, status=404)

            # Проверяем права доступа к папке backups
            backups_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            if not os.path.exists(backups_dir):
                print(f"Creating backups directory: {backups_dir}")  # Отладка
                os.makedirs(backups_dir, exist_ok=True)

            if not os.access(backups_dir, os.W_OK):
                print(f"No write permission for backups directory: {backups_dir}")  # Отладка
                return JsonResponse({'status': 'error', 'message': _("Backups directory lacks write permissions.")}, status=500)

            # Путь к текущей базе данных
            db_path = settings.DATABASES['default']['NAME']
            print(f"Current database path: {db_path}")  # Отладка

            # Проверяем права доступа к файлу базы данных
            if not os.access(db_path, os.W_OK):
                print(f"No write permission for database: {db_path}")  # Отладка
                return JsonResponse({'status': 'error', 'message': _("Database file is read-only or lacks write permissions.")}, status=500)

            # Проверяем права доступа к родительской папке базы данных
            db_dir = os.path.dirname(db_path)
            if not os.access(db_dir, os.W_OK):
                print(f"No write permission for database directory: {db_dir}")  # Отладка
                return JsonResponse({'status': 'error', 'message': _("Database directory lacks write permissions.")}, status=500)

            # Создаём резервную копию текущей базы перед восстановлением
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            current_backup_path = os.path.join(backups_dir, f"pre_restore_{timestamp}.sql")
            print(f"Creating pre-restore backup: {current_backup_path}")  # Отладка
            with open(current_backup_path, 'w', encoding='utf-8') as f:
                process = subprocess.run(['sqlite3', db_path, '.dump'], stdout=subprocess.PIPE, text=True, check=True)
                f.write(process.stdout)

            # Закрываем все соединения с базой данных
            print("Closing database connections")  # Отладка
            connections.close_all()

            # Создаём временную базу данных
            temp_db_path = os.path.join(settings.MEDIA_ROOT, f'temp_restore_{timestamp}.sqlite3')
            print(f"Creating temporary database: {temp_db_path}")  # Отладка

            # Проверяем права доступа к MEDIA_ROOT для временной базы
            if not os.access(settings.MEDIA_ROOT, os.W_OK):
                print(f"No write permission for media directory: {settings.MEDIA_ROOT}")  # Отладка
                return JsonResponse({'status': 'error', 'message': _("Media directory lacks write permissions.")}, status=500)

            # Создаём пустую временную базу
            open(temp_db_path, 'a').close()
            os.chmod(temp_db_path, 0o664)  # Устанавливаем права для временного файла

            # Проверяем права доступа к временной базе
            if not os.access(temp_db_path, os.W_OK):
                print(f"No write permission for temporary database: {temp_db_path}")  # Отладка
                return JsonResponse({'status': 'error', 'message': _("Temporary database file lacks write permissions.")}, status=500)

            # Восстанавливаем базу из SQL-дампа
            print(f"Restoring SQL dump to temporary database: {temp_db_path}")  # Отладка
            with open(backup_path, 'r', encoding='utf-8') as f:
                sql_dump = f.read()
                conn = sqlite3.connect(temp_db_path)
                try:
                    conn.executescript(sql_dump)
                    conn.commit()
                finally:
                    conn.close()

            # Заменяем текущую базу восстановленной
            print(f"Replacing current database with restored: {db_path}")  # Отладка
            os.replace(temp_db_path, db_path)

            # Логирование
            UserActionLog.objects.create(
                user=request.user,
                action_type='restore_backup',
                details=f"Restored database from SQL backup '{filename}'",
                performed_by=request.user
            )

            print("Database restored successfully")  # Отладка
            return JsonResponse({'status': 'success', 'message': _("Database restored successfully.")})
        except subprocess.CalledProcessError as e:
            print(f"Subprocess error during restore: {str(e)}")  # Отладка
            return JsonResponse({'status': 'error', 'message': f"Failed to process SQL dump: {str(e)}"}, status=500)
        except sqlite3.Error as e:
            print(f"SQLite error during restore: {str(e)}")  # Отладка
            return JsonResponse({'status': 'error', 'message': f"SQLite error: {str(e)}"}, status=500)
        except Exception as e:
            print(f"General error during restore: {str(e)}")  # Отладка
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': _("Invalid request method.")}, status=400)

@login_required
def delete_backup(request):
    if request.user.role != 'admin':
        return JsonResponse({'status': 'error', 'message': _("Only admins can delete backups.")}, status=403)

    if request.method == 'POST':
        filename = request.POST.get('filename')
        try:
            backup_path = os.path.join(settings.MEDIA_ROOT, 'backups', filename)
            if not os.path.exists(backup_path):
                return JsonResponse({'status': 'error', 'message': _("Backup file not found.")}, status=404)

            os.remove(backup_path)

            # Логирование
            UserActionLog.objects.create(
                user=request.user,
                action_type='delete_backup',
                details=f"Deleted SQL backup '{filename}'",
                performed_by=request.user
            )

            return JsonResponse({'status': 'success', 'message': _("Backup deleted successfully.")})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': _("Invalid request method.")}, status=400)