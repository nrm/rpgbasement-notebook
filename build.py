#!/usr/bin/env python3
"""Pack transcripts + catalog summaries + glossary into markdown sources for NotebookLM."""
import csv, hashlib, json, os, re
from pathlib import Path

# соседний репозиторий rpgbasement (RPGBASEMENT_DIR переопределяет путь, например для проверки на копии)
SRC = Path(os.environ.get("RPGBASEMENT_DIR") or Path(__file__).resolve().parent.parent / "rpgbasement")
OUT = Path(__file__).resolve().parent
GROUP = 5

eps = {}
with open(SRC / "episodes.tsv", encoding="utf-8", newline="") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        eps[r["name"]] = r
names = sorted(p.stem for p in (SRC / "transcripts").glob("hoav-*.txt"))
num = lambda n: int(n.split("-")[1])

def head(name, level="##"):
    r = eps[name]
    return (f"{level} Выпуск {num(name)} ({name})\n\n"
            f"Страница: {r['page']}  \nАудио: {r['mp3']}\n")

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def snapshot():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT / "sources").glob("*.md")}

# remember what the previous build produced, then start from a clean sources/ (renamed files must not linger)
before = snapshot()
for p in (OUT / "sources").glob("*.md"):
    p.unlink()

# 1) overview: summaries of all episodes (a section of 00-index.md, written below)
parts = ["## Обзор: резюме всех выпусков\n\n"
         "Подкаст «Ролевой подвал», рубрика «Водим», 3-й сезон: ведущий Вундер водит мегаданжен "
         "Halls of Arden Vul (система OSRIC), соведущий Маса слушает и задаёт вопросы. "
         "Ниже короткое резюме каждого выпуска по порядку.\n"]
for n in names:
    d = json.loads((SRC / "catalog" / f"{n}.json").read_text(encoding="utf-8"))
    parts.append(head(n, "###") + "\n" + d["summary"].strip() + "\n")
overview = "\n".join(parts)

# 2) glossary: canonical names and how the speech recognizer garbled them
rows = []
for line in (SRC / "glossary.tsv").read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    canon, _, var = line.partition("\t")
    rows.append((canon.strip(), [v for v in var.split("|") if v]))
g = ["# Глоссарий имён и названий\n\n"
     "Транскрипты получены автоматическим распознаванием речи, поэтому имена и названия в них часто "
     "искажены. Здесь каноническое написание и варианты, в которых оно встречается в тексте. "
     "Если в транскрипте видна одна из форм справа, имеется в виду имя слева.\n"]
for canon, var in rows:
    g.append(f"- **{canon}**" + (f" — в транскриптах также: {', '.join(var)}" if var else ""))
write(OUT / "sources" / "01-glossary.md", "\n".join(g) + "\n")

# 3) transcripts grouped GROUP episodes per file
files = []
for i in range(0, len(names), GROUP):
    grp = names[i:i + GROUP]
    a, b = num(grp[0]), num(grp[-1])
    fn = f"transcripts-{a:03d}-{b:03d}.md"
    body = [f"# Транскрипты выпусков {a}–{b}\n\n"
            "Формат строки: [чч:мм:сс] Спикер: текст. Спикеры: Вундер (ведущий кампании), Маса (соведущий). "
            "Текст получен распознаванием речи, имена могут быть искажены (см. глоссарий).\n"]
    for n in grp:
        t = (SRC / "transcripts" / f"{n}.txt").read_text(encoding="utf-8").strip()
        body.append(head(n) + "\n" + t + "\n")
    write(OUT / "sources" / fn, "\n".join(body))
    files.append(fn)

# 3b) 00-index.md: table of contents, overview and mention indexes in one source,
# so a new episode changes one shared file in NotebookLM instead of six
file_of = {n: files[i // GROUP] for i, n in enumerate(names)}
cat = {n: json.loads((SRC / "catalog" / f"{n}.json").read_text(encoding="utf-8")) for n in names}
hms = lambda t: f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"
KIND_RU = {"module": "модуль", "system": "система", "rule": "правило", "homerule": "хоумрул",
           "idea": "идея", "event": "событие"}

def mline(n, m):
    return (f"- Выпуск {num(n)} · файл {file_of[n]} · {hms(m['t'])} · {KIND_RU[m['kind']]} · "
            f"**{m['name']}** — {m['what']}")

toc = ["## Оглавление: какой выпуск в каком файле\n",
       "### Файлы\n"]
for fn in files:
    grp = [n for n in names if file_of[n] == fn]
    toc.append(f"- {fn}: выпуски {num(grp[0])}–{num(grp[-1])}")
toc += ["", "### Выпуск → файл\n", "| Выпуск | Файл |", "|---|---|"]
toc += [f"| {num(n)} | {file_of[n]} |" for n in names]

NOTE = ("Это указатель, а не полный список. Для каждого выпуска отобрано 30–43 самых заметных "
        "упоминания: если записи нет, тема всё равно могла обсуждаться, проверьте транскрипты. "
        "Время приблизительное: оно указывает на начало длинной реплики, а не на точное место. "
        "Названия взяты из распознанной речи и могут быть искажены.\n")

def index_section(title, kinds, by_name=False):
    ms = [(n, m) for n in names for m in cat[n]["mentions"] if m["kind"] in kinds]
    out = [f"## {title}\n\n{NOTE}"]
    if by_name:
        groups = {}
        for n, m in ms:
            groups.setdefault(m["name"].casefold(), []).append((n, m))
        for key in sorted(groups):
            g = groups[key]
            eps_l = sorted({num(n) for n, _ in g})
            out.append(f"#### {g[0][1]['name']}\n\nВыпуски: {', '.join(map(str, eps_l))}\n")
            out += [mline(n, m) for n, m in g]
            out.append("")
    else:
        cur = None
        for n, m in ms:
            if n != cur:
                cur = n
                out.append(f"\n#### Выпуск {num(n)} (файл {file_of[n]})\n")
            out.append(mline(n, m))
    return "\n".join(out), len(ms)

indexes = [index_section("Указатель: модули и игровые системы", {"module", "system"}, by_name=True),
           index_section("Указатель: правила и хоумрулы (кутёж, травмы, даунтайм и т. п.)", {"rule", "homerule"}),
           index_section("Указатель: идеи, приёмы, NPC, фракции, места", {"idea"}),
           index_section("Указатель: события игровых сессий и кампании", {"event"})]
n_mentions = sum(c for _, c in indexes)
intro = ("# Навигация: оглавление, обзор выпусков и указатели упоминаний\n\n"
         "Разделы этого файла: оглавление (какой выпуск в каком файле транскриптов), обзор (короткое резюме "
         "каждого выпуска) и четыре указателя упоминаний: модули и системы, правила и хоумрулы, идеи, события.\n\n"
         "Как пользоваться. Сначала найдите тему в обзоре или в указателях: у каждой записи указаны номер "
         "выпуска, файл с транскриптом и время. Затем откройте этот файл и найдите в нём заголовок "
         "«Выпуск N», чтобы прочитать подробности.\n")
write(OUT / "sources" / "00-index.md",
      "\n\n".join([intro, "\n".join(toc), overview] + [t for t, _ in indexes]) + "\n")

# 4) README
write(OUT / "README.md", f"""# Ролевой подвал: «Водим», сезон 3 — тексты выпусков для NotebookLM

Здесь лежат расшифровки всех {len(names)} выпусков третьего сезона рубрики «Водим» подкаста
[«Ролевой подвал»](https://rpgbasement.xyz/), где Вундер водит мегаданжен Halls of Arden Vul (система OSRIC).
Их можно загрузить в [Google NotebookLM](https://notebooklm.google.com/) и задавать вопросы по всему сезону.

## Как пользоваться
1. Скачайте файлы: зелёная кнопка **Code** → **Download ZIP**, распакуйте архив.
2. Откройте NotebookLM и создайте новый блокнот.
3. Нажмите «Добавить источники» и загрузите все файлы из папки `sources/` ({len(files) + 2} файлов, можно выделить сразу все).
4. Спрашивайте. Например:
   - «Какие хоумрулы про травмы использует Вундер и в каких выпусках о них говорили?»
   - «Как устроен кутёж в кампании?»
   - «Что произошло в выпуске 5?»

NotebookLM отвечает со ссылками на источники: по ним можно открыть нужное место в тексте.

## Что в файлах
- `00-index.md` — навигация: короткое резюме каждого выпуска, какой выпуск в каком файле и указатели упоминаний
  (модули, правила и хоумрулы, идеи, события) с номером выпуска и временем.
- `01-glossary.md` — правильное написание имён и названий.
- `transcripts-*.md` — сами расшифровки, по {GROUP} выпусков в файле, со ссылками на страницу и аудио каждого выпуска.

## Важно знать
- Расшифровки сделаны автоматически, поэтому в них есть ошибки, а имена и названия часто искажены.
  Глоссарий помогает: можно попросить NotebookLM сверять имена с ним.
- Указатели неполные: если темы нет в указателе, её всё равно могли обсуждать в выпуске.
- Время в записях приблизительное.

## Права
Все права на выпуски принадлежат авторам подкаста «Ролевой подвал» (https://rpgbasement.xyz/).
Расшифровки опубликованы с их согласия.

""")
print(len(names), "episodes,", len(files), "transcript files")

# what to do in NotebookLM, relative to the previous build
after = snapshot()
added = sorted(n for n in after if n not in before)
changed = sorted(n for n in after if n in before and after[n] != before[n])
removed = sorted(n for n in before if n not in after)
print("\nNotebookLM:")
if not (added or changed or removed):
    print("  без изменений")
for label, lst in (("заменить (удалить старый источник, загрузить новый)", changed),
                   ("добавить", added), ("удалить из блокнота (файла больше нет)", removed)):
    if lst:
        print(f"  {label}:")
        for n in lst:
            print(f"    {n}")
