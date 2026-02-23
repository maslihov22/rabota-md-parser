import json
import pandas as pd

# Читаем JSON
with open('vacancies_all.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Топ-10 вакансий по названию
target_titles = [
    "Salesforce Business Analyst",
    "Business development & Sales manager 1000 eur + %",
    "Production Analyst",
    "Business-Class Travel Advisor",
    "Project Manager",  # Omnisurge
    "Business Analyst",  # XAIRO
    "Product Account Manager (B2B)",
    "Операционный / Офис-менеджер (International Operations Manager)",
    "Freight Broker Account Manager",
    "Business Development Manager"  # Adtelligent
]

found_vacancies = []

for vacancy in data:
    title = vacancy.get('title', '')
    if any(target in title for target in target_titles):
        found_vacancies.append(vacancy)
        if len(found_vacancies) >= 10:
            break

# Выводим полные описания
for i, v in enumerate(found_vacancies, 1):
    print(f"\n{'='*100}")
    print(f"#{i} {v['title']}")
    print(f"{'='*100}")
    print(f"Компания: {v['company']}")
    print(f"Зарплата: {v['salary']}")
    print(f"URL: {v['url']}")
    print(f"\nДополнительная информация:")
    for key, val in v.get('additional_info', {}).items():
        print(f"  • {key}: {val}")
    print(f"\nПОЛНОЕ ОПИСАНИЕ:")
    print(v['description'])
