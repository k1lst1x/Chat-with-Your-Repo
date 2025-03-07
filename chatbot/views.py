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
from django.utils.safestring import mark_safe
import markdown

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

def get_default_branch(owner, repo):
    """Получает основную ветку репозитория."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(api_url)
    if response.status_code == 200:
        return response.json().get("default_branch", "main")
    return "main"  # По умолчанию main, если API недоступно

def download_github_repo(github_url):
    """Скачивает репозиторий GitHub в формате ZIP и сохраняет его в MEDIA_ROOT"""

    # Извлекаем owner и repo из ссылки
    match = re.search(r"github\.com/([^/]+)/([^/]+)", github_url)
    if not match:
        return None, "Invalid GitHub URL"

    owner, repo = match.groups()
    
    default_branch = get_default_branch(owner, repo)
    # Формируем ссылку на ZIP-архив из GitHub
    download_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{default_branch}.zip"

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

LANGUAGE_EXTENSIONS = {
    'Python': ['.py'],
    'JavaScript': ['.js', '.jsx'],
    'TypeScript': ['.ts', '.tsx'],
    'Java': ['.java'],
    'C++': ['.cpp', '.hpp', '.h', '.cc'],
    'C': ['.c', '.h'],
    'Go': ['.go'],
    'PHP': ['.php'],
    'Ruby': ['.rb'],
    'Shell': ['.sh'],
}

def detect_language(file_path):
    """Определяет язык программирования по расширению файла."""
    _, ext = os.path.splitext(file_path)
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        if ext in extensions:
            return language
    return "Unknown"

def extract_code_metadata(file_path):
    """Анализирует содержимое файла и извлекает ключевые импорты, классы и функции."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.readlines()
    except Exception as e:
        return {'error': str(e)}

    imports = []
    classes = []
    functions = []

    for line in content:
        line = line.strip()

        # Поиск импортов
        if re.match(r'^\s*(import|from)\s+[\w.]+', line):
            imports.append(line)

        # Поиск классов
        if re.match(r'^\s*class\s+\w+', line):
            classes.append(line)

        # Поиск функций
        if re.match(r'^\s*def\s+\w+', line) or re.match(r'^\s*function\s+\w+', line):
            functions.append(line)

    return {
        'imports': imports,
        'classes': classes,
        'functions': functions
    }

def analyze_repository(repo_path, depth=0):
    """Рекурсивно анализирует файлы в репозитории, учитывая вложенные папки."""
    analysis = {'directories': {}, 'files': {}}

    for root, dirs, files in os.walk(repo_path):
        relative_path = os.path.relpath(root, repo_path)

        # Список папок (чтобы видеть структуру)
        analysis['directories'][relative_path] = dirs

        for file in files:
            file_path = os.path.join(root, file)
            language = detect_language(file_path)
            if language == "Unknown":
                continue  # Пропускаем файлы, которые не являются кодом

            file_analysis = extract_code_metadata(file_path)

            analysis['files'][file_path] = {
                'relative_path': relative_path,
                'language': language,
                'imports': file_analysis.get('imports', []),
                'classes': file_analysis.get('classes', []),
                'functions': file_analysis.get('functions', []),
            }

    return analysis

def summarize_repository(repo_analysis):
    """Создает текстовый отчет о репозитории для передачи в OpenAI."""
    summary = ["📌 Анализ репозитория:\n"]

    for file, details in repo_analysis['files'].items():
        summary.append(f"📄 {file}\n"
                       f"📌 Язык: {details['language']}\n"
                       f"📥 Импорты: {len(details['imports'])}\n"
                       f"📦 Классы: {len(details['classes'])}\n"
                       f"🔧 Функции: {len(details['functions'])}\n")

    return "\n".join(summary)


def analyze_and_ask_openai(repo_path):
    """Анализирует репозиторий и отправляет данные в GPT."""
    repo_analysis = analyze_repository(repo_path)  # Локальный анализ
    summary_text = summarize_repository(repo_analysis)  # Генерация отчета

    # Дополнительно выбираем ключевые файлы для отправки в OpenAI
    key_files_content = []
    for file_path, details in repo_analysis['files'].items():
        if "main" in file_path.lower() or "settings" in file_path.lower() or "config" in file_path.lower():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    key_files_content.append(f"📂 {file_path}\n```{file_content[:2000]}```\n")
            except Exception:
                continue  # Пропускаем файлы, которые не удалось прочитать

    openai_prompt = (
        "Ты — эксперт по анализу кода. Дай детальное объяснение структуры проекта:\n\n"
        + summary_text +
        "\n\nВот содержимое ключевых файлов:\n" +
        "\n".join(key_files_content)
    )

    openai_response = ask_openai(openai_prompt)

    # return f"{summary_text}\n\n💡 OpenAI анализ:\n{openai_response}"
    return f"💡Анализ репозитория:\n{openai_response}"

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

            # response_text = f"Repository downloaded and extracted to: {repo_path}"
            response_text = analyze_and_ask_openai(repo_path)
        else:
            response_text = ask_openai(message)

        # 🔹 **Форматируем ответ в Markdown/HTML**
        response_text = markdown.markdown(
            response_text,
            extensions=['fenced_code', 'tables', 'nl2br', 'extra'],
            output_format="html5"  # Добавь эту строку
        )

        chat = Chat.objects.create(
            user=user, message=message, response=response_text, created_at=timezone.now()
        )

        return JsonResponse({'message': message, 'response': response_text})

    return render(request, 'home.html', {'chats': chats})
