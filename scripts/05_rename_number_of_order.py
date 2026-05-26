import pandas as pd
import random
from datetime import datetime

def generate_deterministic_filename(old_filename, index):
    extension = old_filename.split('.')[-1] if '.' in old_filename else ''

    new_name = f"Check-{index+1:06d}"
    
    if extension:
        new_name += f".{extension}"
    
    return new_name

def generate_time_sosedi(old_date):
    period = random.choices(['morning', 'afternoon'], weights=[70, 30])[0]
    
    if period == 'morning':
        hour = random.randint(9, 12)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
    else:
        hour = random.randint(15, 20)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
    
    new_date = datetime(
        year=old_date.year,
        month=old_date.month,
        day=old_date.day,
        hour=hour,
        minute=minute,
        second=second
    )
    
    return new_date

def generate_time_edostavka(old_date):
    period = random.choices(['morning', 'afternoon'], weights=[20, 80])[0]
    
    if period == 'morning':
        hour = random.randint(6, 8)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
    else:
        hour = random.randint(18, 23)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
    
    return datetime(
        year=old_date.year,
        month=old_date.month,
        day=old_date.day,
        hour=hour,
        minute=minute,
        second=second
    )

def process_csv(input_file, output_file):
    df = pd.read_csv(input_file)
    
    unique_checks = df.groupby(['Файл', 'Дата заказа']).first().reset_index()[['Файл', 'Дата заказа', 'Магазин']]
    
    file_mapping = {}
    date_mapping = {}

    for idx, row in unique_checks.iterrows():
        old_file = row['Файл']
        old_date_str = row['Дата заказа']
        shop_name = row['Магазин']
        
        new_file = generate_deterministic_filename(old_file, idx)
        file_mapping[old_file] = new_file
        
        old_date = pd.to_datetime(old_date_str)
        
        if shop_name == 'sosedi':
            new_date = generate_time_sosedi(old_date)
        else:
            new_date = generate_time_edostavka(old_date)

        date_mapping[old_date_str] = new_date.strftime('%Y-%m-%d %H:%M:%S')
    
    # df['Файл'] = df['Файл'].map(file_mapping)
    df['Дата заказа'] = df['Дата заказа'].map(date_mapping)
    
    df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"✅ Файл сохранен: {output_file}")
    
    return df

def get_time_range(time_slots, slot_name):
    """Вспомогательная функция для вывода диапазона времени"""
    for slot in time_slots:
        if slot["name"] == slot_name:
            return f"{slot['start']:02d}:00-{slot['end']:02d}:00"
    return ""

if __name__ == "__main__":
    input_filename = "../data/processed/all_checks_big.csv"
    output_filename = "../data/processed/processed_file.csv"
    
    process_csv(input_filename, output_filename)
