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
from langchain_community.vectorstores import Chroma
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
import shutil

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

CHROMA_DB_DIR = os.path.join(settings.BASE_DIR, "chroma_db")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def index_repository_for_rag(repo_path, repo_name, user_id):
    documents = []
    for root, _, files in os.walk(repo_path):
        for filename in files:
            if filename.endswith(('.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rb', '.php', '.html', '.css')):
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    rel_path = os.path.relpath(file_path, repo_path)
                    doc = Document(
                        page_content=content,
                        metadata={
                            "file_path": rel_path,
                            "repo_name": repo_name,
                            "user_id": str(user_id)
                        }
                    )
                    documents.append(doc)
                except Exception:
                    continue

    if not documents:
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = splitter.split_documents(documents)

    vectorstore_path = os.path.join(CHROMA_DB_DIR, f"{user_id}_{repo_name}")
    if os.path.exists(vectorstore_path):
        shutil.rmtree(vectorstore_path)

    db = Chroma.from_documents(
        documents=docs,
        embedding=OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
        persist_directory=vectorstore_path
    )
    db.persist()


# def ask_openai(message):
#     response = g4f.ChatCompletion.create(
#         model="gpt-4",
#         messages=[
#             {
#                 "role": "system",
#                 "content": "Your task is to analyze a GitHub repository in great detail. "
#                            "Provide insights on the programming language used, frameworks, libraries, "
#                            "key functions, and any other relevant information about the repository. "
#                            "Offer a structured and detailed breakdown."
#             },
#             {"role": "user", "content": message},
#         ]
#     )
#     return response  # g4f уже возвращает строку

# def ask_openai(message):
#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[
#             {
#                 "role": "system",
#                 "content": "Your task is to analyze a GitHub repository in great detail. "
#                            "Provide insights on the programming language used, frameworks, libraries, "
#                            "key functions, and any other relevant information about the repository. "
#                            "Offer a structured and detailed breakdown."
#             },
#             {"role": "user", "content": message}
#         ]
#     )
#     return response.choices[0].message.content

# from g4f import ChatCompletion  # ❌
from openai import OpenAI
from django.core.cache import cache  # Для хранения thread_id

client = OpenAI(api_key=OPENAI_API_KEY)

def ask_openai(message, user_id="default"):
    # Используем Redis/Django cache, чтобы хранить тред для каждого пользователя
    thread_key = f"openai_thread_{user_id}"
    thread_id = cache.get(thread_key)

    if not thread_id:
        thread = client.beta.threads.create()
        thread_id = thread.id
        cache.set(thread_key, thread_id, timeout=None)

    # Добавляем сообщение
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    # Запускаем ран
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=OPENAI_ASSISTANT_ID
    )

    # Ждем завершения run
    import time
    while True:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status in ["failed", "cancelled"]:
            return "❌ Ошибка: Запрос не удалось обработать."
        time.sleep(1)

    # Получаем ответ
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value
    return last_message

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

def query_repository(question, repo_name, user_id):
    vectorstore_path = os.path.join(CHROMA_DB_DIR, f"{user_id}_{repo_name}")
    if not os.path.exists(vectorstore_path):
        return "❌ Репозиторий не найден. Сначала проанализируйте его."

    db = Chroma(
        persist_directory=vectorstore_path,
        embedding_function=OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    )

    relevant_docs = db.similarity_search(question, k=10)
    context = "\n\n".join([doc.page_content[:1000] for doc in relevant_docs])
    print(context)

    prompt = (
        f"Ты помощник, анализирующий код. Ответь на вопрос пользователя, используя этот контекст:\n\n{context}\n\n"
        f"Вопрос: {question}"
    )

    return ask_openai(prompt, user_id=user_id)


def analyze_and_ask_openai(repo_path, user_id):
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
    index_repository_for_rag(repo_path, os.path.basename(repo_path), user_id=user_id)

    openai_prompt = (
        "Ты — эксперт по анализу кода. Дай детальное объяснение структуры проекта:\n\n"
        + summary_text +
        "\n\nВот содержимое ключевых файлов:\n" +
        "\n".join(key_files_content)
    )

    openai_response = ask_openai(openai_prompt, user_id="analyzer")

    # return f"{summary_text}\n\n💡 OpenAI анализ:\n{openai_response}"
    return f"💡Анализ репозитория:\n{openai_response}"

from datetime import date
from django.db.models import Count

@login_required
def chatbot(request):
    user = request.user
    chats = Chat.objects.filter(user=user)

    if request.method == 'POST':
        message = request.POST.get('message')

        # 🔒 Временно отключаем проверку на подписку
        # if not user.is_subscribed:
        #     from payments.models import Payment
        #     from payments.views import get_payment_link
        #     last_payment = Payment.objects.filter(user=user, status="UNPAID").last()
        #     if last_payment:
        #         payment_url = f"https://stage-checkout.ioka.kz/orders/{last_payment.ioka_order_id}"
        #     else:
        #         response = get_payment_link(request)
        #         payment_url = json.loads(response.content.decode("utf-8")).get("url")
        #     return JsonResponse({
        #         'message': message,
        #         'response': f'У вас нет активной подписки. Оплатите её по ссылке: <a href="{payment_url}" target="_blank">Оплатить</a>'
        #     })

        if not message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        # 📊 Лимит 10 запросов в день
        today = date.today()
        daily_count = Chat.objects.filter(user=user, created_at__date=today).count()
        if daily_count >= 1000:
            response_text = (
                '🛑 Вы достигли лимита в 10 запросов на сегодня. '
                'Подождите до завтра или оформите подписку для безлимитного доступа.'
            )
            return JsonResponse({'message': message, 'response': response_text})

        # 🧠 Обработка GitHub ссылки или обычного запроса
        github_link = re.search(r"https?://github\.com/[^\s]+", message)
        if github_link:
            repo_path, error = download_github_repo(github_link.group(0))
            if error:
                return JsonResponse({'message': message, 'response': f"Ошибка: {error}"})
            response_text = analyze_and_ask_openai(repo_path, user_id=user.id)
        if message.lower().startswith("вопрос по репо:"):
            parts = message.split(":", 2)
            if len(parts) == 3:
                repo_name = parts[1].strip()
                question = parts[2].strip()
                response_text = query_repository(question, repo_name, user.id)
            else:
                response_text = "⚠️ Формат должен быть: 'Вопрос по репо: repo_name: ваш вопрос'"
        else:
            response_text = ask_openai(message, user_id=user.id)

        # 🔹 Форматирование Markdown → HTML
        response_text = markdown.markdown(
            response_text,
            extensions=['fenced_code', 'tables', 'nl2br', 'extra'],
            output_format="html5"
        )

        # 💬 Сохраняем сообщение
        chat = Chat.objects.create(
            user=user, message=message, response=response_text, created_at=timezone.now()
        )

        return JsonResponse({'message': message, 'response': response_text})

    return render(request, 'home.html', {'chats': chats, 'github_token': GITHUB_TOKEN})

def index(request):
    return render(request, 'index.html')