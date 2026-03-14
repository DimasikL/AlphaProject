import pandas as pd
from ast import literal_eval

# Читаем датасет
df = pd.read_csv('dataset/train_dataset.tsv', sep='\t')

# Парсим колонки target и entity из строк в списки
df['target_parsed'] = df['target'].apply(literal_eval)
df['entity_parsed'] = df['entity'].apply(lambda x: literal_eval(x) if x != 'empty' else [])

# Собираем уникальные таргеты и все примеры entity для каждого
target_entities = {}

for _, row in df.iterrows():
    targets = row['target_parsed']
    entities = row['entity_parsed']

    for i, (start, end, label) in enumerate(targets):
        if label not in target_entities:
            target_entities[label] = []
        if i < len(entities):
            target_entities[label].append(entities[i])

# Выводим результат
for label, entities in target_entities.items():
    print(f"\n{'='*60}")
    print(f"Target: {label}")
    print(f"Количество примеров: {len(entities)}")
    print(f"Уникальных примеров: {len(set(entities))}")
    print(f"{'-'*60}")
    for e in sorted(set(entities)):
        print(f"  • {e}")

# Сохранение в JSON
import json

output = {label: sorted(set(entities)) for label, entities in target_entities.items()}
with open('target_entities.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n\nСохранено в target_entities.json")