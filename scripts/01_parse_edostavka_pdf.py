import os
import re
import pandas as pd
from pathlib import Path
import pdfplumber
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

def extract_text_from_pdf(pdf_path):
    """Извлекает текст из PDF-файла"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Ошибка при чтении {pdf_path}: {e}")
    return text

def extract_date_from_text(text):
    """Извлекает дату заказа из текста чека"""
    # Формат 1: YYYY-MM-DD HH:MM:SS
    date_pattern1 = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'
    match = re.search(date_pattern1, text)
    if match:
        return match.group(1)
    
    # Формат 2: YYYY.MM.DD HH:MM:SS
    date_pattern2 = r'(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})'
    match = re.search(date_pattern2, text)
    if match:
        return match.group(1).replace('.', '-')
    
    # # Формат 3: DD.MM.YYYY HH:MM:SS
    # date_pattern3 = r'(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2})'
    # match = re.search(date_pattern3, text)
    # if match:
    #     return match.group(1).replace('.', '-')
    
    # Формат 4: ищем в конце текста
    lines = text.split('\n')
    for line in reversed(lines[-15:]):
        date_match = re.search(r'(\d{4}[.-]\d{2}[.-]\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        if date_match:
            return date_match.group(1).replace('.', '-')
    
    return None

def extract_total_amount(text):
    """Извлекает итоговую сумму чека (с учетом скидки)"""
    lines = text.split('\n')
    
    # Вариант 1: Ищем "Итого" с суммой сразу после (без пробела)
    for i, line in enumerate(lines):
        # Ищем паттерн "Итого117.80 р." или "Итог117.80 р."
        match = re.search(r'Итог(?:о)?\s*(\d+\.?\d*)\s*[р]', line)
        if match:
            return float(match.group(1))
        
        # Ищем "Итог" на отдельной строке, сумма на следующей
        if re.search(r'^Итог\s*$', line.strip()):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                match = re.search(r'(\d+\.?\d*)\s*[р]', next_line)
                if match:
                    return float(match.group(1))
    
    # Вариант 2: Ищем в самом конце текста после "Картой"
    match = re.search(r'Картой\s*\n\s*(\d+\.?\d*)\s*[р]', text)
    if match:
        return float(match.group(1))
    
    # Вариант 3: Ищем просто "Итого" с суммой в любом месте
    match = re.search(r'Итог(?:о)?\s*(\d+\.?\d*)\s*р', text)
    if match:
        return float(match.group(1))
    
    return None

def parse_check_text_robust(text, filename):
    """НАДЕЖНЫЙ парсинг чеков с обработкой всех проблем"""
    
    # Извлекаем дату и итоговую сумму
    order_date = extract_date_from_text(text)
    total_amount = extract_total_amount(text)
    
    # Магазин (все чеки из "Соседи")
    shop_name = "edostavka"
    
    # Разбиваем на строки
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    # Паттерны для пропуска служебных строк
    skip_patterns = [
        r'^Закрытое', r'^"Интернет', r'^Чек продажи', r'^Платёжный',
        r'^Номер док', r'^УНП', r'^Рег\.', r'^Сер\.', r'^Кассир',
        r'^Валюта', r'^Номер заказа', r'^Товары', r'^Итого', 
        r'^Оплачено', r'^Сертификат', r'^Спасибо', r'^Скидка',
        r'^[A-Z0-9]{16,}$', r'^Наличными', r'^Картой', r'^Итог$'
    ]
    
    items = []
    i = 0
    
    while i < len(lines):
        current_line = lines[i]
        
        # Пропускаем служебные строки
        if any(re.match(p, current_line) for p in skip_patterns):
            i += 1
            continue
        
        # Ищем строку с ценой (содержит 'x' и цифры)
        if 'x' in current_line and re.search(r'[\d\.]+\s*x\s*[\d\.]+', current_line):
            price_line = current_line
            
            # Очищаем строку цены
            price_line = re.sub(r'\s*[pр]\.?$', '', price_line)
            price_line = re.sub(r'Скидка\s+[\d\.]+\s*[pр]\.?', '', price_line)
            
            # Парсим количество, цену и итог
            match = re.search(r'([\d\.]+)\s*x\s*([\d\.]+)\s+([\d\.]+)', price_line)
            if match:
                quantity = float(match.group(1))
                price_per_unit = float(match.group(2))
                total = float(match.group(3))
                
                # Собираем название товара (предыдущие строки)
                product_parts = []
                j = i - 1
                
                while j >= 0:
                    prev_line = lines[j]
                    
                    # Если предыдущая строка содержит цену - стоп
                    if 'x' in prev_line and re.search(r'[\d\.]+\s*x\s*[\d\.]+', prev_line):
                        break
                    
                    # Пропускаем служебные
                    if any(re.match(p, prev_line) for p in skip_patterns):
                        break
                    
                    # Пропускаем строки-числа
                    if re.match(r'^[\d\.]+\s*[pр]\.?$', prev_line):
                        break
                    
                    # Очищаем строку
                    clean_line = re.sub(r'^\[M\]\s*', '', prev_line)
                    clean_line = re.sub(r'\s+[pр]\.?$', '', clean_line)
                    
                    if clean_line and not re.match(r'^[\d\.]+$', clean_line):
                        product_parts.insert(0, clean_line)
                    
                    j -= 1
                
                product_name = ' '.join(product_parts) if product_parts else "Неизвестно"
                product_name = re.sub(r'\s+', ' ', product_name).strip()
                
                # Определяем единицу измерения
                if re.search(r'кг\b', product_name.lower()):
                    unit = 'кг'
                elif re.search(r'\d+г\b|г\b|г\)', product_name.lower()):
                    unit = 'г'
                elif re.search(r'л\b', product_name.lower()):
                    unit = 'л'
                else:
                    unit = 'шт'
                
                # Извлекаем вес единицы
                weight_per_unit = extract_weight_from_name(product_name)
                
                items.append({
                    'Магазин': shop_name,
                    'Файл': filename,
                    'Дата заказа': order_date if order_date else 'Не найдена',
                    'Товар': product_name,
                    'Количество': quantity,
                    'Единица': unit,
                    'Вес единицы': weight_per_unit,
                    'Цена за единицу (BYN)': price_per_unit,
                    'Итого (BYN)': total,
                    'Сумма чека (BYN)': total_amount if total_amount else None
                })
                i += 1
            else:
                i += 1
        else:
            i += 1
    
    return items

def process_all_checks(directory_path):
    """Обрабатывает все PDF-файлы в директории"""
    all_items = []
    pdf_files = list(Path(directory_path).glob("*.pdf"))
    
    if not pdf_files:
        print(f"PDF-файлы не найдены в {directory_path}")
        return pd.DataFrame()
    
    print(f"Найдено {len(pdf_files)} PDF-файлов\n")
    
    for pdf_path in pdf_files:
        print(f"📄 Обработка: {pdf_path.name}")
        text = extract_text_from_pdf(pdf_path)
        
        if text:
            items = parse_check_text_robust(text, pdf_path.name)
            all_items.extend(items)
            print(f"   ✅ Извлечено {len(items)} позиций")
            
            if items and items[0]['Сумма чека (BYN)']:
                print(f"   💰 Сумма чека: {items[0]['Сумма чека (BYN)']:.2f} BYN")
            print()
        else:
            print(f"   ❌ Не удалось извлечь текст\n")
    
    return pd.DataFrame(all_items)

def analyze_checks(df):
    """Анализирует распарсенные чеки"""
    if df.empty:
        print("Нет данных для анализа")
        return
    
    print("\n" + "="*80)
    print("📊 АНАЛИЗ ЧЕКОВ")
    print("="*80)
    
    # Основная статистика
    print(f"\n📈 ОСНОВНАЯ СТАТИСТИКА:")
    print(f"   Магазин: {df['Магазин'].iloc[0] if not df.empty else 'Н/Д'}")
    print(f"   Всего чеков: {df['Файл'].nunique()}")
    print(f"   Всего позиций: {len(df)}")
    print(f"   Общая сумма: {df['Итого (BYN)'].sum():.2f} BYN")
    print(f"   Средний чек: {df.groupby('Файл')['Итого (BYN)'].sum().mean():.2f} BYN")
    
    # Покупки по датам
    print(f"\n📅 ПОКУПКИ ПО ДАТАМ:")
    df_with_dates = df[df['Дата заказа'] != 'Не найдена']
    if not df_with_dates.empty:
        # Преобразуем дату для сортировки
        df_with_dates['Дата заказа_dt'] = pd.to_datetime(df_with_dates['Дата заказа'])
        date_summary = df_with_dates.groupby('Дата заказа_dt').agg({
            'Итого (BYN)': 'sum',
            'Товар': 'count'
        }).round(2)
        date_summary.columns = ['Сумма', 'Кол-во позиций']
        
        for date, row in date_summary.iterrows():
            print(f"   {date.strftime('%Y-%m-%d')}: {row['Сумма']:.2f} BYN ({int(row['Кол-во позиций'])} товаров)")
    
    # Топ товаров
    print(f"\n🏆 ТОП-10 ТОВАРОВ ПО СУММЕ:")
    top_products = df.groupby('Товар')['Итого (BYN)'].sum().sort_values(ascending=False).head(10)
    for i, (product, total) in enumerate(top_products.items(), 1):
        print(f"   {i:2}. {product[:55]:55} {total:8.2f} BYN")
    
    # Топ категорий (упрощенно)
    print(f"\n📂 ПОПУЛЯРНЫЕ КАТЕГОРИИ:")
    categories = {
        'Фрукты': ['яблоко', 'банан', 'груша', 'клементин', 'мандарин', 'апельсин', 'киви', 'авокадо', 'хурма', 'манго'],
        'Овощи': ['картофель', 'морковь', 'капуста', 'лук', 'огурец', 'помидор', 'томат', 'свекла', 'редис'],
        'Молочные': ['молоко', 'йогурт', 'творог', 'кефир', 'сметана', 'сливки', 'масло сл'],
        'Мясо': ['фарш', 'сосиски', 'сардельки', 'голень', 'бекон', 'курица', 'индейка'],
        'Бакалея': ['крупа', 'мак.изд', 'мука', 'хлопья', 'кофе', 'чай']
    }
    
    category_totals = {}
    for cat, keywords in categories.items():
        total = 0
        for product, amount in zip(df['Товар'], df['Итого (BYN)']):
            if any(kw in product.lower() for kw in keywords):
                total += amount
        if total > 0:
            category_totals[cat] = total
    
    for cat, total in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
        print(f"   {cat}: {total:.2f} BYN")

# ========== ИСПОЛЬЗОВАНИЕ ==========

if __name__ == "__main__":
    # Укажите путь к директории с PDF-чеками
    directory = "../data/raw/checks_edostavka_shop"  # Замените на ваш путь
    
    # Парсим все чеки
    df_all = process_all_checks(directory)
    
    if not df_all.empty:
        # Сохраняем результат в CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = f"../data/processed/edostavka_{timestamp}.csv"
        df_all.to_csv(csv_file, index=False, encoding='utf-8-sig')
        print(f"\n💾 Сохранено в {csv_file}")
        
        # Показываем первые строки
        print("\n" + "="*80)
        print("📋 ПЕРВЫЕ 15 СТРОК ТАБЛИЦЫ")
        print("="*80)
        print(df_all.head(15).to_string(index=False))
        
        # Анализируем данные
        analyze_checks(df_all)
        
        # Детальная сводка по каждому чеку
        print("\n" + "="*80)
        print("📄 ДЕТАЛЬНАЯ СВОДКА ПО КАЖДОМУ ЧЕКУ")
        print("="*80)
        
        for filename in df_all['Файл'].unique():
            check_df = df_all[df_all['Файл'] == filename]
            total = check_df['Итого (BYN)'].sum()
            check_total = check_df['Сумма чека (BYN)'].iloc[0] if not check_df['Сумма чека (BYN)'].isna().all() else None
            date = check_df['Дата заказа'].iloc[0]
            
            print(f"\n📄 {filename}")
            print(f"   📅 Дата: {date}")
            print(f"   💰 Сумма по позициям: {total:.2f} BYN")
            if check_total:
                print(f"   💰 Сумма из чека: {check_total:.2f} BYN")
                if abs(total - check_total) > 0.01:
                    print(f"   ⚠️ Расхождение: {abs(total - check_total):.2f} BYN")
            print(f"   📦 Товаров: {len(check_df)}")
            
            # Топ-5 товаров в чеке
            print(f"   🏆 Топ-5 товаров:")
            top_items = check_df.nlargest(5, 'Итого (BYN)')[['Товар', 'Итого (BYN)']]
            for _, row in top_items.iterrows():
                print(f"      - {row['Товар'][:45]:45} {row['Итого (BYN)']:7.2f} BYN")
    
    else:
        print("❌ Не удалось обработать ни одного чека")