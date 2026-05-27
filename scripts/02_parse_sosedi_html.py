# pip install beautifulsoup4

import os
import re
import csv
from bs4 import BeautifulSoup
from datetime import datetime

def extract_weight_from_name(name):
    """Извлекает числовое значение веса/объёма из названия товара (140, 0.93, 500, 0.5 и т.д.)"""
    name_upper = name.upper()
    
    # Специальный случай: формат 1/500 (означает 500 грамм)
    match_fraction = re.search(r'1/(\d+)', name_upper)
    if match_fraction:
        return match_fraction.group(1)
    
    # Специальный случай: 1к (сокращение от 1 кг)
    if re.search(r'1[КК](\b|\s|$)', name_upper):
        return '1'
    
    # Ищем паттерны: 360Г, 0.93Л, 1КГ, 10ШТ, 500Г, 200Г
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*([А-Я]+)', name_upper)
    if match:
        value, unit = match.groups()
        # Проверяем, что это единица веса/объёма/количества
        if unit in ['Г', 'КГ', 'Л', 'ШТ', 'МЛ', 'КК']:  # 'КК' для случаев '1КК' (опечатка/сокращение)
            # Заменяем запятую на точку для float
            return value.replace(',', '.')
    
    return ''

def parse_unit_from_name(name):
    """Извлекает единицу измерения (г, кг, л, шт) из названия товара"""
    name_upper = name.upper()
    # Поиск паттернов: 360Г, 0.93Л, 1КГ, 10ШТ
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*([А-Я]+)', name_upper)
    if match:
        value, unit = match.groups()
        unit_clean = unit.replace('Г', 'г').replace('Л', 'л').replace('КГ', 'кг').replace('ШТ', 'шт')
        if unit_clean in ['г', 'кг', 'л', 'шт']:
            return unit_clean
    # Если не нашли, смотрим по ключевым словам в конце
    if name_upper.endswith('КГ'):
        return 'кг'
    if name_upper.endswith('Г') and not name_upper.endswith('КГ'):
        return 'г'
    if name_upper.endswith('Л'):
        return 'л'
    if name_upper.endswith('ШТ'):
        return 'шт'
    return ''

def parse_html_cheque(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    rows = soup.find_all('tr')
    
    # Извлекаем дату и сумму чека
    date_str = ''
    total_sum = ''
    filename = os.path.basename(filepath)
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 2 and 'Кассир' in cells[0].get_text():
            # строка вида "Кассир К Крючкова Е" и дата справа
            date_cell = cells[1].get_text(strip=True)
            # дата вида "23.03.2026 19:58:39"
            if re.search(r'\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}', date_cell):
                date_str = date_cell
        if len(cells) >= 2 and 'ИТОГО К ОПЛАТЕ' in cells[0].get_text():
            total_sum = cells[1].get_text(strip=True)
    
    # Парсим товары: идём по строкам и собираем
    items = []
    i = 0
    while i < len(rows):
        row = rows[i]
        cells = row.find_all('td')
        if len(cells) == 1 and cells[0].has_attr('colspan') and cells[0]['colspan'] == '4':
            # Название товара (colspan=4, align=left)
            product_name = cells[0].get_text(strip=True)
            # Проверяем, что это не заголовок и не пустота
            if product_name and not product_name.startswith('*') and not product_name.startswith('ИТОГО') and not product_name.startswith('БАНК.КАРТА') and not product_name.startswith('Кассир') and product_name != '':
                # Ищем следующую строку с ценой, количеством, итогом
                if i+1 < len(rows):
                    price_row = rows[i+1]
                    price_cells = price_row.find_all('td')
                    if len(price_cells) == 4:
                        price = price_cells[1].get_text(strip=True)
                        quantity = price_cells[2].get_text(strip=True).replace('x', '')
                        line_total = price_cells[3].get_text(strip=True)
                        
                        try:
                            qty = float(quantity)
                        except:
                            qty = 1.0
                        try:
                            price_val = float(price)
                        except:
                            price_val = 0.0
                        
                        unit = parse_unit_from_name(product_name)
                        weight_per_unit = extract_weight_from_name(product_name)
                        
                        # Очистка названия от штрихкода (последнее число 13-14 цифр)
                        product_clean = re.sub(r'\s+\d{13,14}$', '', product_name)
                        
                        items.append({
                            'product': product_clean,
                            'quantity': qty,
                            'unit': unit,
                            'weight_per_unit': weight_per_unit,
                            'price_per_unit': price_val,
                            'line_total': float(line_total) if line_total else 0.0
                        })
        i += 1
    
    result = []
    dt_obj = datetime.strptime(date_str, "%d.%m.%Y %H:%M:%S")

    for item in items:
        result.append({
            'shop': 'sosedi',
            'file': filename,
            'date': dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
            'product': item['product'],
            'quantity': item['quantity'],
            'unit': item['unit'],
            'weight_per_unit': item['weight_per_unit'],
            'price_per_unit': item['price_per_unit'],
            'line_total': item['line_total'],
            'cheque_total': total_sum
        })
    return result

# Папка с HTML-файлами
folder = '../data/raw/checks_sosedi_shop'  # укажите вашу папку
all_data = []

for fname in os.listdir(folder):
    if fname.endswith('.html'):
        filepath = os.path.join(folder, fname)
        try:
            data = parse_html_cheque(filepath)
            all_data.extend(data)
            print(f"Обработан: {fname} -> {len(data)} товаров")
        except Exception as e:
            print(f"Ошибка в {fname}: {e}")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_file = f"../data/processed/sosedi_{timestamp}.csv"

# Сохраняем в CSV с новой колонкой
with open(csv_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['Файл', 'Дата заказа', 'Товар', 'Количество', 'Единица', 'Вес единицы', 'Цена за единицу (BYN)', 'Итого (BYN)', 'Сумма чека (BYN)'])
    for row in all_data:
        writer.writerow([
            row['shop'],
            row['file'],
            row['date'],
            row['product'],
            row['quantity'],
            row['unit'],
            row['weight_per_unit'],
            row['price_per_unit'],
            row['line_total'],
            row['cheque_total']
        ])

print(f"\nГотово! Сохранено {len(all_data)} записей в sosedi_cheques_parsed.csv")