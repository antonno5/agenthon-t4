"""Human-readable report from frozen results. Does not select models or predict."""
import argparse
import json
from pathlib import Path
import statistics


NAMES = {'legacy_v1': 'Старый V1 + общие цитаты', 'naive': 'Наивный прогноз', 'rules': 'Простые правила',
         'ridge': 'Ridge', 'trees': 'Деревья', 'ensemble': 'Среднее трёх методов'}
FAMILIES = {'auction_btc': 'Аукционы', 'yield_change': 'Изменение доходности',
            'yield_direction': 'Направление', 'yield_ranking': 'Ранжирование'}


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    dev = read(root / 'reports/dev.json')
    holdout = read(root / 'reports/holdout.json')
    gate = read(root / 'reports/gate.json')
    selection = read(root / 'reports/selection.json')
    validation = read(root / 'reports/validation.json')
    exploratory = read(root / 'reports/exploratory.json')['comparisons']
    dataset = read(root / 'dataset.json')
    times = [read(p)['wall_seconds'] for p in (root / 'answers').glob('*/*/resources.json')]
    method = selection['method']
    delta = holdout['methods'][method]['mean'] - holdout['methods']['legacy_v1']['mean']
    lines = ['# Результат независимого мини-демо T4, v2', '',
             f"На development выбран **{NAMES[method]}**. На новом holdout 2022–2024: **{gate['selected_holdout_score']:.4f}**, "
             f"разница со старым V1 на этих же заданиях **{delta:+.4f}**.", '',
             '**Это локальный исследовательский балл, не результат leaderboard. Посылок не было.**', '',
             '| Метод | Development 2017–2019 | Holdout 2022–2024 | Ошибки на holdout |',
             '|---|---:|---:|---:|']
    for key, name in NAMES.items():
        lines.append(f"| {name} | {dev['methods'][key]['mean']:.4f} | {holdout['methods'][key]['mean']:.4f} | {holdout['methods'][key]['failures']} |")
    lines += ['', 'В таблице показаны все заранее выбранные кандидаты. Победитель выбирался только по development; таблица holdout не является основанием переключиться на другой метод.', '',
              '| Метод | Аукционы | Изменение доходности | Направление | Ранжирование |', '|---|---:|---:|---:|---:|']
    for key, name in NAMES.items():
        values = holdout['methods'][key]['families']
        lines.append('| ' + name + ' | ' + ' | '.join(f'{values[f]:.4f}' for f in FAMILIES) + ' |')
    lines += ['', '## Что проверено', '',
              f"- {len(dataset['cases'])} задач, {sum(c['entities'] for c in dataset['cases'])} исходных прогнозируемых строк; по шести методам — {validation['forecast_rows_across_six_methods']} прогнозов.",
              f"- {validation['historical_training_and_calibration_examples']} исторических примеров train/calibration после фильтрации. Исключено {validation['excluded_noncausal_examples']} повторяющихся примеров с неверной временной постановкой.",
              f"- {validation['exact_claims_across_six_methods']} точных цитат; хеши исходных ответов и всех входов проверены.",
              '- Семь unit-тестов и пять атак на реальный интерфейс оценщика: потеря сущности, дубль, NaN, выдуманная цитата, неизвестный документ.',
              '- Один input на контейнер, сеть выключена, ответы и другие задачи не монтируются. Лимиты: 2 CPU, 2 GiB RAM.',
              f"- Медиана времени на задачу сразу для всех шести методов: {statistics.median(times):.2f} с; суммарно {sum(times):.1f} с. Загрузка данных, сборка образа и оценщик сюда не входят.",
              '- Вызовов нейросети: **0**. Извлечение, прогнозы, интервалы и цитаты вычисляются скриптами.', '',
              '## Условие отправки', '',
              f"`submit = {str(gate['submit']).lower()}`. Буквальный порог пользователя: score > {gate['threshold']}. Область текущей официальной сырой метрики — [0,1], поэтому порог недостижим без уточнения шкалы.", '',
              f"Разница выбранного метода с наивным: {gate['paired_delta_vs_naive']:+.4f}; парный 95%-й bootstrap-интервал по {gate['independent_time_blocks']} кварталам: [{gate['paired_95_percent_ci'][0]:+.4f}; {gate['paired_95_percent_ci'][1]:+.4f}]. Если выбран сам наивный метод, нулевая разница означает отсутствие улучшения над ним, а не доказательство точности прогноза.", '',
              'Дополнительно не выполнены: полное покрытие семейств T4, подтверждённые исторические версии данных и полный официальный production verifier. Использованы формулы scorer 5.2.2 и проверки точных цитат; `rankable=false`.', '',
              '## Практический вывод', '',
              f"На новом периоде Ridge дал {holdout['methods']['ridge']['mean']:.4f} против {holdout['methods']['naive']['mean']:.4f} у наивного метода. Смесь дала {holdout['methods']['ensemble']['mean']:.4f}. Разбивка выше показывает, в каких семействах есть выигрыш. Эти исследовательские результаты не меняют заранее зафиксированный выбор: {NAMES[method]}.", '',
              f"Дополнительный, не использованный для выбора метода парный bootstrap Ridge минус naive: {exploratory['ridge']['delta_vs_naive']:+.4f}, 95%-й интервал [{exploratory['ridge']['paired_95_percent_ci'][0]:+.4f}; {exploratory['ridge']['paired_95_percent_ci'][1]:+.4f}]. Это исследовательская проверка без поправки на сравнение нескольких методов и с малым числом временных блоков. Она не превращает Ridge в заранее выбранного победителя и не доказывает улучшение на других семействах T4.", '',
              'Следующий эксперимент стоит направить на переносимость отбора между рыночными режимами, реальные vintage-публикации и расширение семейств, заранее выделив новый нераскрытый тест. Результаты этой версии не позволяют обещать улучшение на всех заданиях организатора.', '',
              'Три типа заданий по доходности используют одну историю. Корпуса сгенерированы в трёх известных форматах; произвольные документы и живой House-поиск не тестировались. Происхождение данных и научные источники: [LAB_RESEARCH.md](LAB_RESEARCH.md). Команды: [LAB_README.md](LAB_README.md).', '',
              'Первый прогон сохранён в `test-output/independent-demo/`. Актуальная версия: `test-output/independent-demo-v2/`; её `preregister.json` описывает исправление и новый holdout. Полные машинные отчёты находятся в `reports/`.']
    args.out.write_text('\n'.join(lines) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
