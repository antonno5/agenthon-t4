# Мини-демо T4 на cero

Рабочая копия: `/home/antonnos/agenthon-t4-lab`, ветка `research/t4-algorithmic-lab`.
Актуальные данные, задачи, ответы и отчёты: `test-output/independent-demo-v2/`.
Первый прогон сохранён отдельно в `test-output/independent-demo/`; причина исправления — в исследовании.

Схема: `task + corpus → проверка дат/сущностей → извлечение → численные признаки → прогноз + интервал → точные цитаты → отдельная оценка → закрытый gate отправки`.

| Задание | Вход | Выход |
|---|---|---|
| Аукцион | Прошлые bid-to-cover того же срока | Bid-to-cover следующего аукциона и 90%-й интервал |
| Доходность | До 1000 доступных дневных наблюдений 2/3/5/7/10/30-летних UST | Изменение через 20 наблюдений, в базисных пунктах, и интервал |
| Направление | Та же история доходностей | `up`, если изменение положительное; иначе `non-up` |
| Ранжирование | Те же шесть сроков | Численные изменения, по которым оценщик сравнивает порядок |

В `reports/dev.json` и `reports/holdout.json` есть результаты каждой задачи, метрики и ошибки. `reports/selection.json` содержит выбранный на development метод. `reports/gate.json` содержит решение об отправке и причины. Ответы каждого метода и аудит временных границ лежат в `answers/{dev,holdout}/<task>/`.

Запуск нового эксперимента (новый каталог данных обязателен; раскрытый holdout повторно не используется для подбора):

```sh
cd /home/antonnos/agenthon-t4-lab
python3 -m lab.fetch --root test-output/NEW_VERSION
python3 -m lab.build --root test-output/NEW_VERSION
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/Agenthon-2026/track4-analysis-public.git test-output/NEW_VERSION/official-track4
git -C test-output/NEW_VERSION/official-track4 checkout 1c744e1d6725340643a533f436517d72b53ca0e1
sudo -n docker build -f Dockerfile.lab -t agenthon-t4:algorithmic-lab-v2 .
sudo -n docker run --rm --network=none agenthon-t4:algorithmic-lab-v2 -m unittest discover -s tests -p test_lab.py -v
python3 -u -m lab.run --root test-output/NEW_VERSION --split dev
python3 -u -m lab.run --root test-output/NEW_VERSION --split holdout
python3 -m lab.finalize --root test-output/NEW_VERSION --out LAB_RESULTS.md
```

Одно и то же прошлое допускается повторно использовать для воспроизводимости, но после раскрытия 2020–2024 эти годы уже не новый holdout для улучшенных методов. Для следующего честного выбора нужно заранее выделить другой ещё не использованный период/источник и новую версию плана. Исходный Docker base `agenthon-t4:checker` локален; точный итоговый image ID фиксируется в `runtime.json`. Это рецепт для cero, не переносимая публичная поставка.

`agent_v6` пока поддерживает только явно описанные форматы демо, не произвольные документы организатора. Полной совместимости с публичными заданиями T4 и готовности к отправке не заявляется. Исследование методов и все ограничения: [LAB_RESEARCH.md](LAB_RESEARCH.md).

Полученные результаты: [LAB_RESULTS.md](LAB_RESULTS.md). `lab.finalize` использует зафиксированный image ID, дополняет отсутствующие проверки и собирает отчёт; прогнозы и выбранный метод он не меняет. Исследовательские интервалы сравнения методов сохраняются отдельно в `reports/exploratory.json` и не участвуют в gate.
