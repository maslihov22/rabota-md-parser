import openpyxl
import re
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console

def extract_salary_number(salary_str):
    """Извлекает максимальное число из строки зарплаты"""
    if not salary_str or salary_str == "Не указано" or salary_str == "Не указана":
        return 0

    # Ищем все числа в строке
    numbers = re.findall(r'\d+\s?\d*', str(salary_str))
    if not numbers:
        return 0

    # Берём максимальное
    max_num = max([int(n.replace(' ', '')) for n in numbers])

    # Конвертируем в евро если нужно
    if 'евро' in salary_str.lower() or 'eur' in salary_str.lower():
        return max_num * 20  # примерно к MDL
    elif 'долл' in salary_str.lower() or 'usd' in salary_str.lower() or '$' in salary_str:
        return max_num * 18

    return max_num

def score_vacancy(row_data):
    """Оценивает вакансию по критериям"""
    title = str(row_data.get('Название', '')).lower()
    company = str(row_data.get('Компания', '')).lower()
    salary = str(row_data.get('Зарплата', ''))
    description = str(row_data.get('Описание', '')).lower()

    score = 0
    reasons = []

    # RED FLAGS - автоисключение
    red_flags = [
        'vânzător', 'vanzator', 'продавец', 'casier', 'кассир',
        'call center', 'call-center', 'холодные звонки',
        'agent de paza', 'охранник', 'курьер', 'curier',
        'младший', 'junior developer', 'junior programator',
        'entry level', 'entry-level', 'стажер', 'intern',
        # Sales roles - исключаем холодные продажи
        'sales representative', 'sales manager', 'sales consultant',
        'sales specialist', 'business development & sales', 'bd & sales',
        'sales executive', 'account executive'
    ]

    for flag in red_flags:
        if flag in title or flag in description[:500]:
            return -1000, ["❌ RED FLAG: " + flag]

    # Дополнительная проверка описания на sales-контекст
    sales_description_flags = [
        'sales department', 'sales team',
        'close sales', 'closing sales', 'profitable sales',
        'sales targets', 'sales quota', 'meet sales',
        'cold calling', 'cold calls', 'холодные звонки',
        'продажи по телефону', 'телефонные продажи'
    ]

    for flag in sales_description_flags:
        if flag in description[:1000]:  # Проверяем первую 1000 символов
            return -1000, ["❌ RED FLAG (sales): " + flag]

    # Проверка на требование паспорта ЕС (кроме молдавского биометрического)
    eu_passport_flags = [
        'паспорт ес', 'паспорт еc', 'eu passport',
        'european passport', 'румынский паспорт', 'romanian passport',
        'болгарский паспорт', 'bulgarian passport',
        'citizenship of eu', 'гражданство ес'
    ]

    # Исключения - если явно написано что молдавский биометрический подходит
    md_passport_ok = any(phrase in description.lower() for phrase in [
        'биометрический паспорт молдовы', 'паспорт молдовы', 'moldovan passport',
        'молдавский паспорт', 'cetățenie moldovenească'
    ])

    if not md_passport_ok:
        for flag in eu_passport_flags:
            if flag in description[:1000].lower():
                return -1000, ["❌ RED FLAG: Требуется паспорт ЕС (у тебя только MD биометрический)"]

    # SALARY - CRITICAL FILTER (минимум $1500 = 27k MDL)
    salary_num = extract_salary_number(salary)
    if salary_num > 0 and salary_num < 27000:
        # Если ЗП указана но ниже $1500 - автоисключение
        return -1000, [f"❌ ЗП слишком низкая: {salary_num} MDL (минимум 27000)"]

    if salary_num >= 27000:  # $1500+
        score += 100
        reasons.append(f"+100 💰 ОТЛИЧНАЯ ЗП: {salary_num} MDL")
    elif salary_num == 0 and company not in ['не указано', 'не указана', '']:
        # ЗП не указана - даём шанс, но меньше баллов
        score += 30
        reasons.append("+30 зп не указана (может быть высокая)")

    # INTERNATIONAL EXPOSURE - TOP PRIORITY (+100 points)
    # Проверяем РЕАЛЬНЫЕ командировки vs работа в travel agency
    travel_sales_context = ['travel agency', 'travel advisor', 'travel consultant',
                            'travel representative', 'travel specialist',
                            'sell travel', 'book travel', 'travel booking',
                            'air ticket', 'booking flights', 'premium travel',
                            'luxury travel', 'first class travel', 'business class travel']

    # Проверяем И в title, И в description
    is_travel_sales = any(ctx in description for ctx in travel_sales_context) or \
                      any(ctx in title for ctx in travel_sales_context)

    # Ищем РЕАЛЬНЫЕ командировки
    real_travel_keywords = ['командировк', 'поездк', 'relocation', 'relocate',
                            'работа за границ', 'work abroad', 'business trip',
                            'delegation', 'международные поездки',
                            'attend conferences', 'represent company abroad']

    found_travel = False
    for kw in real_travel_keywords:
        if kw in description:
            if is_travel_sales:
                # Работа в travel agency - меньше баллов
                score += 30
                reasons.append("+30 🎫 Travel industry (продажа билетов)")
                found_travel = True
                break
            else:
                # РЕАЛЬНЫЕ командировки!
                score += 100
                reasons.append("+100 🌍 РЕАЛЬНЫЕ КОМАНДИРОВКИ!")
                found_travel = True
                break

    # Просто "travel" упомянуто без контекста
    if not found_travel and 'travel' in description:
        if is_travel_sales:
            score += 20
            reasons.append("+20 работа в travel сфере")
        else:
            score += 50
            reasons.append("+50 travel-related work")

    # INTERNATIONAL CONTEXT (не командировки, но international team)
    intl_keywords = ['international team', 'global team', 'работа с international',
                     'english-speaking', 'remote team', 'distributed team']
    intl_found = False
    for kw in intl_keywords:
        if kw in description:
            score += 50
            reasons.append("+50 🌐 International team")
            intl_found = True
            break

    # Просто "international" или "global" в описании
    if not intl_found:
        if 'international' in description or 'global' in description:
            score += 20
            reasons.append("+20 international context")

    # VISIBILITY & GROWTH - small/growing companies
    visibility_keywords = ['startup', 'scale-up', 'растущ', 'expanding', 'быстро развива',
                          'small team', 'маленькая команда', 'founding team']
    for kw in visibility_keywords:
        if kw in description:
            score += 60
            reasons.append("+60 🚀 Startup/растущая компания (легко выделиться)")
            break

    # EXECUTIVE PROXIMITY - близко к decision makers
    exec_keywords = ['assistant to ceo', 'executive assistant', 'помощник директор',
                     'assistant to founder', 'chief of staff', 'right hand']
    for kw in exec_keywords:
        if kw in title or kw in description[:500]:
            score += 80
            reasons.append("+80 👔 Близко к топ-менеджменту")
            break

    # GOOD ROLES для роста и visibility (БЕЗ sales)
    good_roles = {
        'operations manager': 70, 'operations': 60,
        'coordinator': 55, 'assistant': 50,
        'partnerships': 65, 'partnership manager': 70,
        'account manager': 55,  # Работа с существующими клиентами, НЕ продажи
        'project manager': 60, 'product manager': 65,
        'analyst': 45, 'business analyst': 55,
        'data analyst': 50,
        'strategy': 65, 'chief of staff': 80
    }

    for role, points in good_roles.items():
        if role in title:
            score += points
            reasons.append(f"+{points} роль: {role}")
            break  # Только одна роль

    # TRAINING / CAN LEARN - не обязательно 100% match skills
    learning_keywords = ['обучение', 'training', 'can learn', 'will teach',
                        'we provide training', 'наставник', 'mentor']
    for kw in learning_keywords:
        if kw in description:
            score += 40
            reasons.append("+40 📚 Обучение на месте")
            break

    # GROWTH POTENTIAL explicitly mentioned
    growth_keywords = ['карьерн', 'career growth', 'advancement', 'promotion',
                      'path to', 'перспектив роста', 'быстрый рост']
    for kw in growth_keywords:
        if kw in description:
            score += 50
            reasons.append("+50 📈 Явный рост в карьере")
            break

    # Убрали секцию SALES/BD - теперь sales это red flag

    # KNOWN GOOD COMPANIES (но не гиганты)
    good_companies = ['business class', 'tekwill', 'arnia']  # Убрали Endava, Pentalog (слишком большие)
    if any(comp in company for comp in good_companies):
        score += 40
        reasons.append("+40 🏢 Известная компания")

    # ENGLISH requirement (good sign for international exposure)
    if 'english' in description or 'engleză' in description:
        score += 25
        reasons.append("+25 🗣 English required")

    return score, reasons

# Читаем Excel быстро через pandas
console = Console()
console.print("\n[cyan]📊 Загружаем vacancies_all.xlsx...[/cyan]")

import pandas as pd

# Pandas читает НАМНОГО быстрее чем openpyxl
df = pd.read_excel('vacancies_all.xlsx', engine='openpyxl')
total_rows = len(df)
console.print(f"[green]✓[/green] Найдено вакансий: [bold]{total_rows}[/bold]\n")

# Анализируем все вакансии с прогресс-баром
scored_jobs = []

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

    task = progress.add_task("[yellow]Анализируем вакансии...", total=total_rows)

    # Обновляем прогресс батчами по 100 вакансий (быстрее)
    batch_size = 100

    for idx, row in df.iterrows():
        row_data = row.to_dict()

        score, reasons = score_vacancy(row_data)

        if score > 0:  # Только положительные
            scored_jobs.append({
                'score': score,
                'reasons': reasons,
                'data': row_data
            })

        # Обновляем прогресс не каждый раз, а батчами
        if idx % batch_size == 0 or idx == total_rows - 1:
            progress.update(task, completed=idx + 1)

# Сортируем по скору
scored_jobs.sort(key=lambda x: x['score'], reverse=True)

# Формируем вывод в строку
output = []
output.append("="*80)
output.append("🔥 ТОП-10 ВАКАНСИЙ ПОД ТВОЙ ПРОФИЛЬ")
output.append("="*80)

for i, job in enumerate(scored_jobs[:10], 1):
    data = job['data']
    output.append(f"\n{'='*80}")
    output.append(f"#{i} | SCORE: {job['score']} баллов")
    output.append(f"{'='*80}")
    output.append(f"📌 Вакансия: {data.get('Название', 'Не указано')}")
    output.append(f"🏢 Компания: {data.get('Компания', 'Не указано')}")
    output.append(f"💰 Зарплата: {data.get('Зарплата', 'Не указано')}")
    output.append(f"🔗 URL: {data.get('URL', '')}")
    output.append(f"\n💡 Почему подходит:")
    for reason in job['reasons']:
        output.append(f"   {reason}")

    desc = str(data.get('Описание', ''))
    if desc and desc != 'Описание не найдено':
        output.append(f"\n📝 ПОЛНОЕ ОПИСАНИЕ:")
        output.append(desc)

output.append(f"\n{'='*80}")
output.append(f"✓ Всего подходящих вакансий: {len(scored_jobs)}")
output.append(f"✓ Отфильтровано мусора: {total_rows - len(scored_jobs)}")
output.append(f"{'='*80}")

# Выводим в консоль
result_text = '\n'.join(output)
print(result_text)

# Сохраняем в файл
with open('top10_vacancies.txt', 'w', encoding='utf-8') as f:
    f.write(result_text)
