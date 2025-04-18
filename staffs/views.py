import csv
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from .models import Document, Organization, User, UserActionLog, Notification
from .forms import SendDocumentForm, CustomUserCreationForm, OrganizationCreationForm
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
from django.views.decorators.http import require_POST
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
        django_messages.error(request, _("You do not have permission to view this document."))
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
            django_messages.error(request, _("File not found on server: ") + file_path)
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
                        django_messages.warning(request, _("The DOCX file is empty or contains no readable text."))
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
        django_messages.warning(request, _("No file attached to this document."))
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
        django_messages.error(request, _("You do not have permission to download this page."))
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


# views.py

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

    users = User.objects.all()

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

    organizations = Organization.objects.all()
    role_choices = User.ROLES

    context = {
        'users': page_obj,
        'page_obj': page_obj,
        'organizations': organizations,
        'role_choices': role_choices,
        'current_org': org_filter,
        'current_role': role_filter,
        'stats': stats,
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

            # Удаление файла с диска, если он существует
            if document.document_content:
                if os.path.isfile(document.document_content.path):
                    os.remove(document.document_content.path)
                document.document_content = None  # Очищаем поле
                document.save()

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
                action_type='add_organization',  # Предполагается, что этот тип действия добавлен в ACTION_TYPES
                details=f"Added new organization '{organization.name}'",
                performed_by=request.user
            )

            django_messages.success(request, _("Organization added successfully!"))
            return redirect('staffs:dashboard')
    else:
        form = OrganizationCreationForm()

    return render(request, 'staffs/add_organization.html', {'form': form})