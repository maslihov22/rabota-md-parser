import requests
from bs4 import BeautifulSoup
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console

BASE_URL = "https://www.rabota.md"
SEARCH_URL = "https://www.rabota.md/ru/jobs-moldova"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_total_pages():
    """Определяем количество страниц"""
    response = requests.get(SEARCH_URL, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Ищем заголовок с количеством вакансий: "9050 вакансий"
    title_h1 = soup.find('h1', id='SearchTitle')

    if title_h1:
        span = title_h1.find('span', class_='font-normal')
        if span:
            text = span.get_text(strip=True)  # "9050 вакансий"
            # Вытаскиваем число
            total_vacancies = int(''.join(filter(str.isdigit, text)))
            # На странице ~40 вакансий, округляем вверх
            total_pages = (total_vacancies + 39) // 40
            return total_pages

    # Fallback: парсим пагинацию
    pagination_links = soup.find_all('a', href=True)
    max_page = 1

    for link in pagination_links:
        href = link['href']
        if '/page-' in href:
            try:
                page_num = int(href.split('/page-')[-1].split('?')[0])
                max_page = max(max_page, page_num)
            except ValueError:
                continue

    return max_page

def parse_job_links(page_num):
    """Собираем ссылки на вакансии со страницы"""
    if page_num == 1:
        url = SEARCH_URL
    else:
        url = f"{SEARCH_URL}/page-{page_num}"

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')

    job_links = []

    # Ищем контейнеры вакансий
    vacancy_cards = soup.find_all('div', class_='vacancyCardItem')

    if vacancy_cards:
        # Если нашли карточки вакансий
        for card in vacancy_cards:
            link = card.find('a', href=True)
            if link:
                href = link['href']
                # Проверяем оба паттерна: /ru/locuri-de-munca/ и /ru/joburi/
                if ('/ru/locuri-de-munca/' in href or '/ru/joburi/' in href) and not href.startswith('javascript:'):
                    full_url = BASE_URL + href if not href.startswith('http') else href
                    job_links.append(full_url)
    else:
        # Fallback: ищем все ссылки на вакансии
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            if '/ru/locuri-de-munca/' in href and href.count('/') >= 4:
                full_url = BASE_URL + href if not href.startswith('http') else href
                if full_url not in job_links:
                    job_links.append(full_url)

    return job_links

def parse_job_details(job_url):
    """Парсим детали конкретной вакансии"""
    try:
        response = requests.get(job_url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Заголовок вакансии
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Не указано"

        # Компания - несколько вариантов
        company = "Не указано"
        company_tag = soup.find('a', class_='company-title')
        if company_tag:
            company = company_tag.get_text(strip=True)
        else:
            # Альтернативный поиск - в div с иконкой компании
            company_divs = soup.find_all('div', class_='flex items-center gap-2')
            for div in company_divs:
                svg = div.find('svg')
                if svg and 'svgCompany' in str(svg):
                    span = div.find('span')
                    if span:
                        company = span.get_text(strip=True)
                        break

        # Зарплата - несколько вариантов
        salary = "Не указано"

        # Вариант 1: в space-y-[3px] с заголовком "Зарплата:"
        salary_divs = soup.find_all('div', class_='space-y-[3px]')
        for div in salary_divs:
            header = div.find('div', class_='text-sm text-gray-400')
            if header and 'Зарплата' in header.get_text():
                value_div = div.find('div', class_='text-sm text-gray-700')
                if value_div:
                    salary = value_div.get_text(strip=True)
                    break

        # Вариант 2: h2 с классом text-primary
        if salary == "Не указано":
            salary_h2 = soup.find('h2', class_='text-primary')
            if salary_h2:
                salary = salary_h2.get_text(strip=True)

        # Вариант 3: div с классом text-primary font-semibold
        if salary == "Не указано":
            salary_div = soup.find('div', class_='text-sm mb-2 text-primary lowercase font-semibold text-center')
            if salary_div:
                salary = salary_div.get_text(strip=True)

        # Описание вакансии - несколько вариантов
        description = "Описание не найдено"

        # Вариант 1: собираем ВСЕ блоки с атрибутом data-js-vacancy-content
        description_divs = soup.find_all('div', attrs={'data-js-vacancy-content': True})
        if description_divs:
            description_parts = []
            for div in description_divs:
                # Клонируем div чтобы не изменять оригинал
                desc_copy = div.__copy__()
                # Удаляем h1 внутри (дубли заголовков)
                for h1_tag in desc_copy.find_all('h1'):
                    h1_tag.decompose()
                text = desc_copy.get_text(separator='\n', strip=True)
                if text:
                    description_parts.append(text)

            if description_parts:
                description = '\n\n'.join(description_parts)
        else:
            # Вариант 2: class inbody
            description_div = soup.find('div', class_='inbody')
            if description_div:
                desc_copy = description_div.__copy__()
                for h1_tag in desc_copy.find_all('h1'):
                    h1_tag.decompose()
                description = desc_copy.get_text(separator='\n', strip=True)

        # Дополнительные поля
        details = {}

        # Ищем все элементы с иконками и текстом
        info_sections = soup.find_all('div', class_='space-y-[3px]')
        for section in info_sections:
            label = section.find('div', class_='text-sm text-gray-400')
            value = section.find('div', class_='text-sm text-gray-700')
            if label and value:
                key = label.get_text(strip=True).replace(':', '')
                val = value.get_text(strip=True)
                if key and val and key != 'Зарплата':  # Зарплату уже добавили отдельно
                    details[key] = val

        return {
            "title": title,
            "url": job_url,
            "company": company,
            "salary": salary,
            "description": description,
            "additional_info": details
        }

    except Exception as e:
        print(f"  Ошибка при парсинге {job_url}: {e}")
        return None

def main():
    console = Console()
    console.print("\n[bold cyan]🚀 Начинаем парсинг вакансий с rabota.md...[/bold cyan]\n")

    # Определяем количество страниц
    total_pages = get_total_pages()
    console.print(f"[green]✓[/green] Найдено страниц: [bold]{total_pages}[/bold]\n")

    all_jobs = []

    # Собираем все ссылки на вакансии параллельно
    all_job_links = []
    seen_urls = set()
    links_lock = threading.Lock()

    def fetch_page_links(page_num, progress_obj, task_id):
        """Собираем ссылки с одной страницы"""
        job_links = parse_job_links(page_num)
        progress_obj.update(task_id, advance=1)
        time.sleep(random.uniform(0.3, 0.7))
        return job_links

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console
    ) as progress:

        page_task = progress.add_task("[cyan]Собираем ссылки со страниц...", total=total_pages)

        # Парсим страницы параллельно (5 потоков для страниц)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(fetch_page_links, page, progress, page_task): page
                for page in range(1, total_pages + 1)
            }

            total_found = 0
            total_duplicates = 0

            for future in as_completed(futures):
                try:
                    job_links = future.result()
                    total_found += len(job_links)
                    # Добавляем только уникальные ссылки
                    with links_lock:
                        new_links = [link for link in job_links if link not in seen_urls]
                        duplicates = len(job_links) - len(new_links)
                        total_duplicates += duplicates
                        all_job_links.extend(new_links)
                        seen_urls.update(new_links)
                except Exception as e:
                    page = futures[future]
                    console.print(f"[red]✗ Ошибка на странице {page}:[/red] {e}")

    console.print(f"\n[green]✓[/green] Всего найдено ссылок: [bold]{total_found}[/bold]")
    console.print(f"[yellow]⚠[/yellow] Отфильтровано дублей: [bold]{total_duplicates}[/bold]")
    console.print(f"[green]✓[/green] Уникальных вакансий: [bold]{len(all_job_links)}[/bold]\n")

    # Парсим детали каждой вакансии параллельно
    output_file = 'vacancies_all.json'
    file_lock = threading.Lock()

    MAX_WORKERS = 10

    def process_job(job_url, progress_obj, task_id):
        """Обработка одной вакансии"""
        job_data = parse_job_details(job_url)

        if job_data:
            with file_lock:
                all_jobs.append(job_data)
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_jobs, f, ensure_ascii=False, indent=2)

        time.sleep(random.uniform(0.5, 1))
        progress_obj.update(task_id, advance=1)
        return job_data

    # Запускаем параллельную обработку с прогресс-баром
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console
    ) as progress:

        parse_task = progress.add_task("[yellow]Парсим детали вакансий...", total=len(all_job_links))

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_job, url, progress, parse_task): url
                for url in all_job_links
            }

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    url = futures[future]
                    console.print(f"[red]✗ Ошибка:[/red] {url}: {e}")

    console.print(f"\n[bold green]✓ Парсинг завершен![/bold green]")
    console.print(f"[green]✓[/green] Собрано вакансий: [bold]{len(all_jobs)}[/bold]")
    console.print(f"[green]✓[/green] Данные сохранены в [bold]{output_file}[/bold]\n")

if __name__ == "__main__":
    main()
