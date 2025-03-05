import os
import re
import requests
import zipfile
import json
import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.decorators import login_required
from .models import Chat
import g4f
from django.utils.html import escape


def ask_openai(message):
    response = g4f.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "Your task is to analyze a GitHub repository in great detail. "
                           "Provide insights on the programming language used, frameworks, libraries, "
                           "key functions, and any other relevant information about the repository. "
                           "Offer a structured and detailed breakdown."
            },
            {"role": "user", "content": message},
        ]
    )
    return response  # g4f уже возвращает строку

def download_github_repo(github_url):
    """Скачивает репозиторий GitHub в формате ZIP и сохраняет его в MEDIA_ROOT"""

    # Извлекаем owner и repo из ссылки
    match = re.search(r"github\.com/([^/]+)/([^/]+)", github_url)
    if not match:
        return None, "Invalid GitHub URL"

    owner, repo = match.groups()
    
    # Формируем ссылку на ZIP-архив из GitHub
    download_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"

    # Проверяем, существует ли папка MEDIA_ROOT, если нет - создаём
    if not os.path.exists(settings.MEDIA_ROOT):
        os.makedirs(settings.MEDIA_ROOT)

    media_path = os.path.join(settings.MEDIA_ROOT, f"{repo}.zip")

    response = requests.get(download_url, stream=True)
    if response.status_code != 200:
        return None, "Failed to download repository. Check if the repository exists and is public."

    # Сохраняем ZIP-архив
    with open(media_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)

    # Создаём папку для распаковки
    extract_path = os.path.join(settings.MEDIA_ROOT, repo)
    if not os.path.exists(extract_path):
        os.makedirs(extract_path)

    # Проверяем, является ли скачанный файл ZIP-архивом
    try:
        with zipfile.ZipFile(media_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
    except zipfile.BadZipFile:
        return None, "Downloaded file is not a valid ZIP archive."

    return extract_path, None

@login_required
def chatbot(request):
    user = request.user

    chats = Chat.objects.filter(user=user)

    if request.method == 'POST':
        message = request.POST.get('message')
        # Если нет подписки — отправляем ссылку на оплату
        if not user.is_subscribed:
            from payments.models import Payment  # Импортируем модель платежей
            from payments.views import get_payment_link  # Импортируем генерацию ссылки

            # Проверяем, есть ли неоплаченный заказ
            last_payment = Payment.objects.filter(user=user, status="UNPAID").last()
            if last_payment:
                payment_url = f"https://stage-checkout.ioka.kz/orders/{last_payment.ioka_order_id}"
            else:
                # Если заказа нет, создаем новый
                response = get_payment_link(request)
                payment_url = json.loads(response.content.decode("utf-8")).get("url")

            return JsonResponse({
                'message': message,
                'response': f'У вас нет активной подписки. Оплатите её по ссылке: <a href="{payment_url}" target="_blank">Оплатить</a>'
            })


        if not message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        # Проверяем, содержит ли сообщение ссылку на GitHub
        github_link = re.search(r"https?://github\.com/[^\s]+", message)
        if github_link:
            repo_path, error = download_github_repo(github_link.group(0))
            if error:
                return JsonResponse({'error': error}, status=400)

            response_text = f"Repository downloaded and extracted to: {repo_path}"
        else:
            response_text = ask_openai(message)

        chat = Chat.objects.create(
            user=user, message=message, response=response_text, created_at=timezone.now()
        )

        return JsonResponse({'message': message, 'response': response_text})

    return render(request, 'home.html', {'chats': chats})
