#!/usr/bin/env python3
# coding: utf-8
"""
Собирает статический сайт из исходников проекта.

Вход:
  source/Лендинг ПЭ 4.0.dc.html   — шаблон DesignCraft (React-разметка)
  source/assets/viola-hero.png    — портрет для первого экрана
  Страницы-к-публикации/*.html    — фрагменты правовых документов (pandoc)
  build-assets/fonts/*.woff2      — подшитые шрифты

Выход: site/ — семь страниц, ноль внешних запросов.

Запуск:
  python3 build.py                          сборка под свой домен
  python3 build.py --base /Viola-Maro       сборка под подпуть (GitHub Pages)
  python3 build.py --noindex                запретить индексацию (превью)
  python3 build.py --mode pre --out site/pre   версия предзаписи
  python3 build.py --mode bron --out site/bron страница брони
  python3 build.py --mode zayavka --out site/zayavka   заявка: цены есть,
                                              оплаты на странице нет

Сборка под домен pre.viola-maro.ru — предзапись в корне, оплата в /pay/,
правовые страницы в одном экземпляре:

  python3 build.py --mode pre --out dist --cname pre.viola-maro.ru
  python3 build.py --out dist/pay --base /pay --docs-root

Куски для вставки в блок T123 Тильды:

  python3 build.py --mode pre --out tilda-src --tilda tilda
"""

import base64
import hashlib
import html as html_mod
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "source")
LEGAL = os.path.join(ROOT, "Страницы-к-публикации")
BUILD_ASSETS = os.path.join(ROOT, "build-assets")
OUT = os.path.join(ROOT, "site")

TG_NAME = "@violamaroteam"          # аккаунт службы заботы
TG = "https://t.me/" + TG_NAME[1:]  # ссылка и подпись — из одного места
EMAIL = "mg.ananizh@gmail.com"
CARE_HOURS = "пн–пт, 10:00–18:00\u00a0МСК"

# Аккаунт отдела заботы. Рядом с ним всегда стоит строка «Пишем только
# с этого аккаунта»: человеку, который платит незнакомой команде, важнее
# знать, с чего ему напишут, чем куда обратиться — поддельные «менеджеры»
# в Telegram после оплаты обычная история.
#
# Список, а не одна строка: если аккаунтов снова станет несколько, блок
# и текст соберутся сами, без правок вёрстки.
CARE_ACCOUNTS = (
    ("Отдел заботы", TG_NAME, TG),
)
CARE_ONLY = ("Пишем только с\u00a0этого аккаунта."
             if len(CARE_ACCOUNTS) == 1 else
             "Пишем только с\u00a0этих аккаунтов.")

# Телефонный кадр режется из того же снимка, что и десктопный: одно фото
# на оба экрана, иначе на десктопе одно выражение лица, а на телефоне другое.
# ── Телефонный кадр: привязка к лицу ────────────────────────────────────
#
# Прежние подходы задавали кадр под один размер экрана и разъезжались на
# всех остальных: где-то Виолу срезало, где-то она уползала под текст.
# Причина в том, что положение считалось от края кадра, а не от неё самой.
#
# Теперь опорная точка — центр лица. Работает так: object-position: P%
# ставит точку P% изображения ровно в P% рамки, и это верно при ЛЮБОМ
# её размере. Значит, достаточно вырезать кадр так, чтобы лицо оказалось
# на нужной доле ширины, и оно там и останется — на любом телефоне.
#
# Вырезка ниже ставит лицо на 74% ширины и 22% высоты. Эти же числа стоят
# в object-position в base.css — менять их нужно парой.
FACE_X, FACE_Y = 1250, 210        # центр лица в исходнике 1672×941
MOBILE_CROP = (368, 0, 1560, 941) # даёт лицо на 74% ширины кадра

DOCS = [
    ("oferta", "offer", "Публичная оферта"),
    ("prilozhenie-1", "offer-prilozhenie", "Приложение № 1 к Публичной оферте"),
    ("politika-pd", "privacy", "Политика обработки персональных данных"),
    ("soglasie-pd", "consent", "Согласие на обработку персональных данных"),
    ("soglasie-rassylki", "consent-ads", "Согласие на рекламные и информационные сообщения"),
    ("polzovatelskoe-soglashenie", "terms", "Пользовательское соглашение"),
]

DOC_URL = {slug: "/" + url for slug, url, _ in DOCS}

# Все адреса внутри страниц пишутся от корня: так требуют правовые документы
# («/offer», «/privacy» — они названы в тексте оферты и в чекбоксах).
# На GitHub Pages сайт живёт в подпапке /Viola-Maro/, поэтому перед выдачей
# адреса получают префикс. На своём домене BASE пустой и ничего не меняется.
BASE = ""
NOINDEX = False

# Правовые страницы должны лежать в одном экземпляре: у документа обязан
# быть постоянный адрес, версии которого вы храните. Когда обе версии сайта
# живут на одном домене, вторая свои копии не строит, а ссылается на первые.
DOCS_ROOT = False

# Своё имя домена для GitHub Pages: без этого файла он обслуживает
# только адрес вида имя.github.io.
CNAME = ""

# Куда положить куски для вставки в блок T123 Тильды.
TILDA_OUT = ""

# Два сайта из одного шаблона. "pay" — продажа с тарифами и оплатой,
# "pre" — предзапись: без цен, с блоком «что даёт предзапись» и заявкой
# вместо платежа. Девять экранов из одиннадцати у них общие, поэтому
# копией файлов это делать нельзя: правки разъедутся на первой же неделе.
MODE = "pay"

# ── Страница брони ──────────────────────────────────────────────────────
#
# Отдельная короткая страница, ссылку на которую отправляют лично: человек
# уже поговорил с командой и решает вносить бронь. Продавать заново незачем,
# поэтому экраны с программой на ней не выводятся.
#
# Бронь — это АВАНС, а не задаток. Задаток по ст. 380–381 ГК обязан быть
# прямо назван задатком письменно и тянет за собой штрафные последствия
# для обеих сторон; для потребителя это лишний риск. Аванс засчитывается
# в стоимость и возвращается при отказе, как того и требует ст. 32 ЗоЗПП:
# написать «бронь невозвратна» нельзя, такое условие ничтожно.
#
# Заполняется перед выпуском. Пустые значения роняют сборку намеренно:
# страница про деньги не должна выйти с недописанными цифрами.
BOOKING_AMOUNT = "5 000 ₽"
BOOKING_DEADLINE = "1 октября"        # день старта потока
BOOKING_PAY_URL = ""                  # страница оплаты брони в GetPlatinum

# Формулировка про судьбу брони при неоплате остатка.
#
# Заказчик просил «невозвратная». Так писать нельзя, и запрещает это не
# закон вообще, а п. 8.1 их собственной оферты: «Право Заказчика на отказ
# от Договора не может быть ограничено настоящей Офертой. Условия,
# ущемляющие права потребителя по сравнению с законодательством, ничтожны.»
# Строка «бронь не возвращается» на странице противоречила бы договору,
# на который эта же страница ссылается.
#
# Поэтому то же по сути, но как перенос, а не как утрата: деньги остаются
# у человека, просто в другом потоке.
#
# Строку про порядок возврата с самой страницы заказчик просил снять — это
# его право: рекламировать возврат страница не обязана, раздел 8 оферты
# от этого никуда не девается. Чего на странице быть не может, так это
# обратного утверждения «бронь не возвращается»: оно прямо спорило бы
# с п. 8.1 договора, на который эта же страница ссылается.
BOOKING_CARRY = ("Если не доплатите до старта, бронь переносится "
                 "на следующий поток или на другой продукт Виолы Маро&nbsp;— "
                 "и засчитывается в его стоимость.")

# Заказчик хочет невозвратную бронь, оформленную как отдельная услуга
# «сохранение условий». Переключатель заведён заранее, но включать его
# нельзя, пока юрист не пропишет такую услугу в оферте: сегодня п. 8.1
# даёт безусловное право на отказ, и надпись «невозвратно» спорила бы
# с договором, на который ссылается сама страница.
#
# Запрос юристу — Страницы-к-публикации/_ЗАПРОС-юристу-бронь-как-услуга.md
# Включать только вместе с новой редакцией оферты.
BOOKING_AS_SERVICE = False

CHANNEL_URL = "https://t.me/+iIqJoSn2UBU3Yzky"

# ── Страница события «Неудобные» ────────────────────────────────────────
#
# Отдельный лендинг на три дня, к практикуму отношения не имеет: своя
# разметка (build-assets/neudobnye.html) и свои стили (neudobnye.css).
# Общее с остальным сайтом — шапка, подвал, cookie-полоса, шрифты,
# палитра и портрет на первом экране: правовые ссылки и реквизиты
# обязаны быть теми же самыми, а Виола — той же самой.
#
# Адреса платёжных страниц заказчик присылает отдельно. Пока пусто,
# кнопки никуда не ведут и сборка говорит об этом вслух: страница про
# деньги не должна тихо выйти с мёртвыми кнопками.
NEUD_PAY_RUB = ""    # оплата в рублях (в ней же рассрочка)
NEUD_PAY_INTL = ""   # оплата с зарубежной карты

# Два разных срока, и путать их нельзя.
#
#   подарки  — до 23 августа, дальше сгорают. На него же идёт таймер.
#   цена     — до 4 сентября держится самой низкой, дальше растёт.
#
# Даты цены живут в исходном шаблоне (карточки тарифов, финальный экран)
# и здесь не трогаются. Здесь только про подарки.
#
# Правовые документы не трогаются вовсе: в Приложении № 1 свои даты,
# менять их может только юрист.
# Дат у подарков на страницах больше нет: в блоках стоит просто
# «за раннюю оплату». Срок остался только у счётчика под первым экраном
# предзаписи — он тикает до этой отметки и прячется, когда она пройдена.
GIFT_ISO = "2026-08-23T23:59:59+03:00"

ABS_ROOTS = ["assets/"] + [url for _s, url, _t in DOCS]


def apply_base(text):
    """Проставляет префикс подпути всем корневым адресам в готовой странице."""
    if not BASE:
        return text
    text = text.replace('href="/"', 'href="%s/"' % BASE)
    roots = ["assets/"] if DOCS_ROOT else ABS_ROOTS
    for root in roots:
        text = text.replace('"/' + root, '"%s/%s' % (BASE, root))   # href, src
        text = text.replace(" /" + root, " %s/%s" % (BASE, root))   # записи srcset
        text = text.replace("(/" + root, "(%s/%s" % (BASE, root))   # url() в CSS
    return text


# ─────────────────────────────────────────────────────────── данные недель ──
# Перенесено дословно из <script type="text/x-dc"> исходного шаблона.

ICONS = [
    [{"c": [12, 8, 3.4]}, "M5.5 19.5c.9-3.3 3.4-5 6.5-5s5.6 1.7 6.5 5"],
    [{"c": [9, 9, 3]}, {"c": [16.5, 12, 2.4]},
     "M3.5 19c.7-2.8 2.8-4.3 5.5-4.3M13 19c.3-1.9 1.6-2.9 3.5-2.9s3.2 1 3.5 2.9"],
    ["M12 20s-6.5-3.9-6.5-8.4A3.9 3.9 0 0 1 12 9a3.9 3.9 0 0 1 6.5 2.6C18.5 16.1 12 20 12 20z"],
    [{"c": [12, 5, 2.2]}, "M12 8v7M8 10.5h8M9.5 20l2.5-5 2.5 5"],
    ["M12 3.5l2.5 5.2 5.5.8-4 3.9 1 5.6-5-2.7-5 2.7 1-5.6-4-3.9 5.5-.8z"],
    [{"c": [12, 12, 8.2]},
     "M14.5 9.3c-.6-.8-1.5-1.2-2.6-1.2-1.5 0-2.4.8-2.4 1.8 0 2.5 5 1.3 5 3.9 0 1.1-1 2-2.6 2-1.2 0-2.1-.4-2.7-1.2M12 6.6v10.8"],
]

WEEKS = [
    {
        "n": "1", "title": "Фигура эмпата",
        "q": "Кто я такой? Это дар или со мной что-то не так?",
        "lead": "Эмпатия как суперсила. Эмпатия — это природный интеллект, который нужно развивать и использовать. Эмпатия как основа внутренней самоценности. Психология плюс духовность равняется эмпатия.",
        "tricks": "— как отличить эмпатию от слияния и созависимости\n— упражнения на распознавание своего эмпатического канала\n— формирование новой самоидентификации: «Я — эмпат, и это моя сила»",
        "note": "",
    },
    {
        "n": "2", "title": "Эмпат и отношения с людьми",
        "q": "Почему мной пользуются? Как отказать и не чувствовать себя виноватым? Почему на работе больше всех достаётся мне?",
        "lead": "Выход из детской зависимой позиции, позиции жертвы — в созидательную позицию взрослого. Осознанность и личные границы: формирование личного поля защиты от манипуляций эго-зависимых и токсичных людей.",
        "tricks": "— распознавание признаков токсичного взаимодействия\n— техники быстрого возвращения в себя после контакта\n— формирование внутреннего взрослого, который умеет говорить «нет» без чувства вины",
        "note": "",
    },
    {
        "n": "3", "title": "Эмпат-родители и эмпат-дети",
        "q": "Как быть опорой родным и жить при этом свою жизнь? Мой ребёнок эмпат — что ему нужно?",
        "lead": "Как воспитывать своих детей с повышенной чувствительностью и как сепарироваться от опыта детско-родительских отношений. Баланс внутренних и внешних ролей — родители, дети, взрослые.",
        "tricks": "— особенности воспитания высокочувствительных детей\n— практики внутренней сепарации\n— карта внутренних ролей: где я сейчас — Ребёнок, Родитель или Взрослый",
        "note": "",
    },
    {
        "n": "4", "title": "Психосоматика у эмпата",
        "q": "Почему у меня всё время что-то болит, а врачи ничего не находят?",
        "lead": "Формирование психосоматики: этапы и механизмы. Язык психосоматики и как определить её формирование на первых этапах. Области проявления психосоматики.",
        "tricks": "— карта тела: какая эмоция в какую зону уходит\n— признаки начинающейся психосоматики\n— простые телесные практики возвращения контакта с собой",
        "note": "Практикум не заменяет обследование и лечение у врача.",
    },
    {
        "n": "5", "title": "Самореализация людей с повышенной чувствительностью",
        "q": "Как найти своё место? Внутри богато, а снаружи будто всё слишком грубо.",
        "lead": "Как совместить духовное и социальное. Проявленность вовне и раскрытие себя внутри.",
        "tricks": "— поиск своих ниш и форматов самовыражения\n— баланс уединения и социальной активности\n— практики безопасной проявленности",
        "note": "",
    },
    {
        "n": "6", "title": "Психология наполненности и деньги",
        "q": "Почему я не могу удержать деньги? В чём моя ценность?",
        "lead": "Психология наполненности как фундамент жизненного изобилия — в отношениях, в финансах и не только. Состояние наполненности и ресурсности как фундамент благополучия.",
        "tricks": "— диагностика: зарабатываю я из наполненности или из дефицита\n— как отличить денежную мотивацию из пустоты от мотивации из полноты\n— практики возвращения в ресурсность перед финансовыми решениями",
        "note": "",
    },
]


def icon_svg(paths):
    parts = []
    for d in paths:
        if isinstance(d, dict):
            cx, cy, r = d["c"]
            parts.append('<circle cx="%s" cy="%s" r="%s"/>' % (cx, cy, r))
        else:
            parts.append('<path d="%s"/>' % d)
    return ('<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + "".join(parts) + "</svg>")


for i, w in enumerate(WEEKS):
    w["icon"] = icon_svg(ICONS[i])
    w["label"] = "НЕДЕЛЯ " + w["n"]
    w["quote"] = "«" + w["q"] + "»"
    w["items"] = [
        {"i": j + 1, "text": re.sub(r"^—\s*", "", t)}
        for j, t in enumerate(x for x in w["tricks"].split("\n") if x)
    ]


# ─────────────────────────────────────────────── парсинг шаблона .dc.html ──

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(apply_base(text))


def find_block(text, tag, start=0):
    """Возвращает (open_start, body_start, body_end, close_end) первого <tag ...>…</tag>
    с учётом вложенности. None, если тега нет."""
    m = re.compile(r"<%s\b[^>]*>" % tag).search(text, start)
    if not m:
        return None
    depth = 1
    pos = m.end()
    pat = re.compile(r"<%s\b[^>]*>|</%s>" % (tag, tag))
    while depth:
        m2 = pat.search(text, pos)
        if not m2:
            raise ValueError("незакрытый <%s>" % tag)
        depth += 1 if m2.group(0)[1] != "/" else -1
        pos = m2.end()
        if depth == 0:
            return m.start(), m.end(), m2.start(), m2.end()
    return None


def subst(text, mapping):
    def rep(m):
        key = m.group(1).strip()
        return mapping.get(key, m.group(0))
    return re.sub(r"\{\{([^}]*)\}\}", rep, text)


def expand_weeks(tpl):
    """Раскрывает <sc-for list="{{ weeks }}"> и вложенные sc-for / sc-if."""
    blk = find_block(tpl, "sc-for")
    if not blk:
        return tpl
    o, bs, be, ce = blk
    body = tpl[bs:be]
    out = []
    for w in WEEKS:
        chunk = body
        # вложенный sc-for по приёмам недели
        inner = find_block(chunk, "sc-for")
        if inner:
            io, ibs, ibe, ice = inner
            item_tpl = chunk[ibs:ibe]
            items = "".join(
                subst(item_tpl, {"t.i": str(it["i"]), "t.text": html_mod.escape(it["text"])})
                for it in w["items"]
            )
            chunk = chunk[:io] + items + chunk[ice:]
        # sc-if по сноске недели
        cond = find_block(chunk, "sc-if")
        if cond:
            co, cbs, cbe, cce = cond
            keep = chunk[cbs:cbe] if w["note"] else ""
            chunk = chunk[:co] + keep + chunk[cce:]
        chunk = subst(chunk, {
            "w.icon": w["icon"],
            "w.label": w["label"],
            "w.title": html_mod.escape(w["title"]),
            "w.quote": html_mod.escape(w["quote"]),
            "w.lead": html_mod.escape(w["lead"]),
            "w.note": html_mod.escape(w["note"]),
        })
        out.append(chunk)
    return tpl[:o] + "".join(out) + tpl[ce:]


# ────────────────────────────────────── style-hover / active / focus → CSS ──

HOVER_RULES = {}   # css-текст → имя класса


def collect_state_styles(tpl):
    """style-hover="…" на элементе → класс + правило в таблице стилей."""
    tag_re = re.compile(r"<([a-zA-Z][\w-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>")

    def process(m):
        name, attrs = m.group(1), m.group(2)
        states = {}
        for state, pseudo in (("hover", ":hover"), ("active", ":active"), ("focus", ":focus-visible")):
            am = re.search(r'\sstyle-%s="([^"]*)"' % state, attrs)
            if am:
                states[pseudo] = am.group(1).strip()
                attrs = attrs[:am.start()] + attrs[am.end():]
        if not states:
            return m.group(0)
        key = "|".join("%s{%s}" % (p, c) for p, c in sorted(states.items()))
        cls = HOVER_RULES.get(key)
        if not cls:
            cls = "s" + hashlib.md5(key.encode()).hexdigest()[:7]
            HOVER_RULES[key] = cls
        cm = re.search(r'\sclass="([^"]*)"', attrs)
        if cm:
            attrs = attrs[:cm.start()] + ' class="%s %s"' % (cm.group(1), cls) + attrs[cm.end():]
        else:
            attrs = ' class="%s"' % cls + attrs
        return "<%s%s>" % (name, attrs)

    return tag_re.sub(process, tpl)


def hover_css():
    lines = []
    for key, cls in sorted(HOVER_RULES.items(), key=lambda kv: kv[1]):
        for part in key.split("|"):
            pseudo, decl = part.split("{", 1)
            lines.append(".%s%s{%s}" % (cls, pseudo, decl.rstrip("}")))
    return "\n".join(lines)


# ────────────────────────────────────────────────────── контраст текста ──
#
# Замеры на собранной странице показали четыре пары ниже порога 4.5:1 —
# все на светлых карточках тарифов. Значения сдвинуты внутри той же палитры:
# бронза берётся из тёмного акцента #8A5A2B, серые — на два шага темнее.
#
# Отдельно: зачёркнутые пункты «Самостоятельного» давали 3.0:1. Это ровно та
# ошибка, от которой предостерегал бриф: если зачёркнутое сливается в серый
# шум, аргумент тарифа пропадает. Линия зачёркивания тоже усилена.

CONTRAST_FIXES = [
    ("color: #9A9088", "color: #776B61"),                       # 3.00 → 5.01
    ("color: #7D7167", "color: #6E6158"),                       # 4.37 → 5.60
    ("color: #A3835F", "color: #8A5A2B"),                       # 3.38 → 5.66
    ("text-decoration-color: #C9A87F", "text-decoration-color: #8A5A2B"),
    ("margin-top: 1px; color: #C9A87F", "margin-top: 1px; color: #8A5A2B"),
]


def fix_contrast(tpl):
    for old, new in CONTRAST_FIXES:
        tpl = tpl.replace(old, new)
    return tpl


def drop_field(html, name):
    """Убирает <label> целиком вместе с полем name=... внутри."""
    i = html.index('name="%s"' % name)
    a = html.rindex("<label", 0, i)
    b = html.index("</label>", i) + len("</label>")
    return html[:a] + html[b:]


def screen_span(tpl, label):
    """Границы экрана data-screen-label с учётом вложенных div."""
    m = re.search(r'<div[^>]*data-screen-label="%s"[^>]*>' % re.escape(label), tpl)
    if not m:
        raise ValueError("экран не найден: %s" % label)
    depth, pos = 1, m.end()
    pat = re.compile(r"<div\b[^>]*>|</div>")
    while depth:
        m2 = pat.search(tpl, pos)
        if not m2:
            raise ValueError("незакрытый экран: %s" % label)
        depth += -1 if m2.group(0) == "</div>" else 1
        pos = m2.end()
    return m.start(), pos


def drop_screen(tpl, label):
    a, b = screen_span(tpl, label)
    return tpl[:a] + tpl[b:]


def insert_before_screen(tpl, label, html):
    a, _ = screen_span(tpl, label)
    return tpl[:a] + html + tpl[a:]


# ───────────────────────────────────────────────── превращение div → section ──

def divs_to_sections(tpl):
    """Верхнеуровневые экраны data-screen-label → <section aria-label>."""
    out = tpl
    pos = 0
    while True:
        m = re.compile(r'<div([^>]*?)data-screen-label="([^"]*)"([^>]*)>').search(out, pos)
        if not m:
            break
        label = m.group(2)
        # найти парный </div>
        depth = 1
        p = m.end()
        pat = re.compile(r"<div\b[^>]*>|</div>")
        while depth:
            m2 = pat.search(out, p)
            if not m2:
                raise ValueError("незакрытый экран %s" % label)
            depth += -1 if m2.group(0) == "</div>" else 1
            p = m2.end()
        close_start, close_end = p - len("</div>"), p
        attrs = (m.group(1) + m.group(3)).strip()
        aria = re.sub(r"^\d+\w*\s+", "", label)
        opening = '<section %s aria-label="%s">' % (attrs, html_mod.escape(aria))
        out = out[:m.start()] + opening + out[m.end():close_start] + "</section>" + out[close_end:]
        pos = m.start() + len(opening)
    return out


# ──────────────────────────────────────────────────────── общие фрагменты ──

def footer_html(depth_prefix=""):
    docs = "".join(
        '\n        <a href="%s">%s</a>' % (DOC_URL[slug], title)
        for slug, _, title in DOCS
    )
    return """
<footer class="ft" aria-label="Реквизиты и документы">
  <div class="ft-in">
    <div class="ft-grid">

      <div class="ft-col">
        <p class="ft-org">Организатор программ Виолы&nbsp;Маро</p>
        <p class="ft-legal">
          ИП Нижевясова Анна Станиславовна<br>
          ОГРНИП 321695200039136<br>
          ИНН 690503942107<br>
          Зарегистрирована Межрайонной ИФНС России №&nbsp;10 по&nbsp;Тверской области
        </p>
      </div>

      <div class="ft-col">
        <p class="ft-label"><span class="ft-ico" aria-hidden="true">✉</span>e-mail</p>
        <a href="mailto:%(email)s">%(email)s</a>
      </div>

      <div class="ft-col">
        <p class="ft-label"><span class="ft-ico" aria-hidden="true">✈</span>Служба заботы в&nbsp;Telegram</p>
        <a href="%(tg)s" target="_blank" rel="noopener">%(tgname)s</a>
        <p class="ft-hours">пн–пт, 10:00–18:00&nbsp;МСК</p>
      </div>

      <nav class="ft-col ft-docs" aria-label="Правовые документы">
        <p class="ft-label">Документы</p>%(docs)s
      </nav>

    </div>

    <p class="ft-disclaimer">
      Информация на&nbsp;сайте носит информационно-просветительский характер,
      не&nbsp;является медицинской услугой и&nbsp;не&nbsp;заменяет консультацию специалиста. 18+
    </p>
    <p class="ft-copy">
      © Нижевясова А.&nbsp;С., 2026. Все права защищены. Любое использование или
      копирование материалов сайта, элементов дизайна и&nbsp;оформления допускается
      только с&nbsp;письменного разрешения правообладателя и&nbsp;со&nbsp;ссылкой на&nbsp;источник.
    </p>
    <p class="ft-note" id="meta-note">* Meta признана экстремистской организацией в&nbsp;России</p>
  </div>
</footer>
""" % {"email": EMAIL, "tg": TG, "tgname": TG_NAME, "docs": docs}


COOKIE_HTML = """
<div class="cookie-bar" id="cookie-bar" hidden>
  <p>
    Мы используем файлы cookie, чтобы сайт работал корректно и&nbsp;чтобы понимать,
    какие материалы вам полезны. Продолжая пользоваться сайтом, вы&nbsp;соглашаетесь
    с&nbsp;их&nbsp;использованием.
    <a href="/privacy#cookie">Подробнее</a>
  </p>
  <button type="button" id="cookie-ok">Хорошо</button>
</div>
"""

COOKIE_JS = """
(function () {
  var KEY = 'cookie_ok', bar = document.getElementById('cookie-bar');
  if (!bar) return;
  function initAnalytics() {
    /* Сюда — инициализация Яндекс.Метрики и рекламных пикселей.
       До нажатия «Хорошо» ни один аналитический скрипт стартовать не должен. */
  }
  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) {}
  if (stored) { initAnalytics(); return; }
  bar.hidden = false;
  document.getElementById('cookie-ok').addEventListener('click', function () {
    try { localStorage.setItem(KEY, new Date().toISOString()); } catch (e) {}
    bar.hidden = true;
    initAnalytics();
  });
})();
"""


def head(title, description, css_path, extra=""):
    if NOINDEX:
        extra = '<meta name="robots" content="noindex, nofollow">\n' + extra
    return """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<meta name="theme-color" content="#241C18">
<meta property="og:type" content="website">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:locale" content="ru_RU">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="%(css)s">
%(extra)s</head>
<body>
<a class="skip" href="#main">К основному содержанию</a>
""" % {"title": html_mod.escape(title), "desc": html_mod.escape(description),
       "css": css_path, "extra": extra}


# ─────────────────────────────────────────────────────────────── картинки ──

def build_images():
    global MOBILE_WIDTHS, DESKTOP_WIDTHS
    from PIL import Image, ImageFilter
    src = os.path.join(SRC, "assets", "viola-hero.png")
    outdir = os.path.join(OUT, "assets", "img")
    os.makedirs(outdir, exist_ok=True)
    im = Image.open(src).convert("RGB")
    W, H = im.size

    def save(img, name, widths):
        lo, hi = sorted(widths)
        for w in widths:
            suffix = "-sm" if w == lo else ""
            if img.width == w:
                r = img
            else:
                r = img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)
                # уменьшение всегда мылит; слабая нерезкая маска возвращает
                # кромку глаз и волос, не давая ореолов на ровном фоне
                r = r.filter(ImageFilter.UnsharpMask(radius=1.0, percent=55, threshold=3))
            for ext, kw in (("webp", {"quality": 90, "method": 6}),
                            ("jpg", {"quality": 88, "optimize": True, "progressive": True,
                                     "subsampling": 0})):
                p = os.path.join(outdir, "%s%s.%s" % (name, suffix, ext))
                r.save(p, **kw)
                made.append(p)

    made = []
    # десктоп — исходный горизонтальный кадр
    DESKTOP_WIDTHS = (1200, 1672)
    save(im, "hero", DESKTOP_WIDTHS)

    # Телефон. Кадр горизонтальный, а экран вдвое уже, чем высок, поэтому
    # из снимка режется вертикальная часть — от MOBILE_CROP_X до правого края.
    # Слева в ней остаётся полоса пустого фона: на неё ложится текст.
    crop = im.crop(MOBILE_CROP)
    cw = crop.width

    face_x = (FACE_X - MOBILE_CROP[0]) / cw * 100
    face_y = FACE_Y / crop.height * 100
    print("  лицо в кадре: %.0f%% ширины, %.0f%% высоты "
          "(эти доли — в object-position)" % (face_x, face_y))

    mob = crop

    MOBILE_WIDTHS = (620, cw)
    save(mob, "hero-mob", MOBILE_WIDTHS)

    total = sum(os.path.getsize(p) for p in made)
    print("  картинки: %d файлов, %.0f КБ" % (len(made), total / 1024))


def build_geroy_photo():
    """Портрет на первый экран. Вырезка без фона.

    Лицо на снимке измерено по тону кожи, а не прикинуто на глаз: центр
    на 49% ширины и 17,5% высоты, нижняя граница лица на 31% высоты.
    Эти доли лежат в CSS как --face-x и --face-y — на случай, если кадр
    где-то придётся обрезать: object-position ставит точку лица в ту же
    долю рамки при любом её размере.

    Формат — WebP с альфой. PNG того же качества весит вчетверо больше;
    он остаётся запасным, узким и квантованным.
    """
    from PIL import Image
    src = os.path.join(SRC, "assets", "neudobnye-geroy.png")
    outdir = os.path.join(OUT, "assets", "img")
    os.makedirs(outdir, exist_ok=True)

    # Холст НЕ обрезается по альфе намеренно. Кадрирование задаёт окно
    # [data-figclip] в таблице заказчика, и доли там посчитаны от полного
    # кадра 1122×1402. Обрежешь прозрачные поля — рамка уедет и макушка
    # окажется срезанной.
    im = Image.open(src).convert("RGBA")

    made = []
    for w in GEROY_WIDTHS:
        r = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        path = os.path.join(outdir, "geroy%s.webp" % ("-sm" if w == min(GEROY_WIDTHS) else ""))
        r.save(path, quality=88, method=6)
        made.append(path)

    small = im.resize((GEROY_PNG_WIDTH, round(im.height * GEROY_PNG_WIDTH / im.width)),
                      Image.LANCZOS)
    png = os.path.join(outdir, "geroy-sm.png")
    small.quantize(colors=255, method=Image.FASTOCTREE).save(png, optimize=True)
    made.append(png)

    global GEROY_RATIO
    GEROY_RATIO = im.height / im.width
    print("  портрет первого экрана: %d файлов, %.0f КБ"
          % (len(made), sum(os.path.getsize(x) for x in made) / 1024))


GEROY_WIDTHS = (420, 840)
GEROY_PNG_WIDTH = 420
GEROY_RATIO = 1402 / 1122


def geroy_picture():
    lo, hi = GEROY_WIDTHS
    h = round(GEROY_PNG_WIDTH * GEROY_RATIO)
    return ('<picture>'
            '<source type="image/webp" '
            'srcset="/assets/img/geroy-sm.webp %dw, /assets/img/geroy.webp %dw" '
            'sizes="(max-width: 899px) 78vw, 420px">'
            '<img data-geroy="1" src="/assets/img/geroy-sm.png" alt="Виола Маро" '
            'width="%d" height="%d" fetchpriority="high" decoding="async">'
            '</picture>' % (lo, hi, GEROY_PNG_WIDTH, h))
    # Размеры у <img> оставлены: без них браузер не знает пропорций
    # до загрузки и страница прыгает. Кадрирует картинку окно [data-figclip],
    # ширину и высоту ей задаёт таблица заказчика.


def build_avtor_photo():
    """Портрет для экрана «Кто ведёт». Вырезка на бежевом фоне.

    В исходнике это PNG на 1,6 МБ. Отдаётся WebP, JPEG остаётся запасным:
    прозрачности в кадре нет, фон залит, и PNG тут не нужен никому.
    """
    from PIL import Image
    src = os.path.join(SRC, "assets", "viola-cutout-beige.png")
    outdir = os.path.join(OUT, "assets", "img")
    os.makedirs(outdir, exist_ok=True)

    im = Image.open(src).convert("RGB")
    made = []
    for w in AVTOR_WIDTHS:
        r = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        suffix = "-sm" if w == min(AVTOR_WIDTHS) else ""
        for ext, kw in (("webp", {"quality": 86, "method": 6}),
                        ("jpg", {"quality": 84, "optimize": True, "progressive": True})):
            path = os.path.join(outdir, "avtor%s.%s" % (suffix, ext))
            r.save(path, **kw)
            made.append(path)

    print("  портрет автора: %d файлов, %.0f КБ"
          % (len(made), sum(os.path.getsize(x) for x in made) / 1024))


AVTOR_WIDTHS = (560, 840)


def avtor_picture():
    lo, hi = AVTOR_WIDTHS
    return ('<picture>'
            '<source type="image/webp" '
            'srcset="/assets/img/avtor-sm.webp %dw, /assets/img/avtor.webp %dw" '
            'sizes="(max-width: 899px) 86vw, 420px">'
            '<img data-avtor="1" src="/assets/img/avtor-sm.jpg" alt="Виола Маро" '
            'width="%d" height="%d" loading="lazy" decoding="async">'
            '</picture>' % (lo, hi, lo, round(lo * 1448 / 1086)))


MOBILE_WIDTHS = ()
DESKTOP_WIDTHS = ()


def hero_picture():
    mob_lo, mob_hi = sorted(MOBILE_WIDTHS)
    dsk_lo, dsk_hi = sorted(DESKTOP_WIDTHS)

    def src(name, ext, lo, hi):
        return ('/assets/img/%s-sm.%s %dw, /assets/img/%s.%s %dw'
                % (name, ext, lo, name, ext, hi))

    return """<picture>
          <source media="(max-width: 760px)" type="image/webp"
                  srcset="%s"
                  sizes="100vw">
          <source media="(max-width: 760px)" type="image/jpeg"
                  srcset="%s"
                  sizes="100vw">
          <source type="image/webp"
                  srcset="%s"
                  sizes="100vw">
          <img src="/assets/img/hero.jpg"
               srcset="%s"
               sizes="100vw"
               alt="Виола Маро сидит в кресле"
               width="1672" height="941"
               fetchpriority="high" decoding="async">
        </picture>""" % (
        src("hero-mob", "webp", mob_lo, mob_hi),
        src("hero-mob", "jpg", mob_lo, mob_hi),
        src("hero", "webp", dsk_lo, dsk_hi),
        src("hero", "jpg", dsk_lo, dsk_hi))




# ──────────────────────────────────────────── экраны версии предзаписи ──

CTA_BOOK = ('<a href="#bron" data-open-form="Бронь места" data-pay="bron" '
            'style="align-self: center; display: inline-flex; white-space: nowrap; '
            'align-items: center; gap: 14px; '
            'background: linear-gradient(180deg, #F0DCBB 0%, #D9BC92 52%, #C29A6C 100%); '
            'color: #2A211C; text-decoration: none; font-weight: 700; '
            'font-size: clamp(18px, 1.9vw, 22px); letter-spacing: .01em; '
            'padding: 23px 34px 23px 48px; border-radius: 999px; '
            'box-shadow: 0 18px 40px -14px rgba(60,45,32,.45), 0 0 0 1px rgba(194,154,108,.4), '
            '0 0 0 10px rgba(201,168,127,.12), inset 0 1px 0 rgba(255,255,255,.6); '
            'transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;" '
            'style-hover="transform: translateY(-3px); filter: brightness(1.05);" '
            'style-active="transform: translateY(-1px);">Внести бронь'
            '<span style="display: inline-flex; align-items: center; justify-content: center; '
            'width: 34px; height: 34px; border-radius: 50%; background: rgba(42,33,28,.9); '
            'color: #F0DCBB; font-size: 16px; line-height: 1;">→</span></a>')

CTA_DARK = ('<a href="#zapis" data-open-form="Предзапись" style="align-self: center; '
            'display: inline-flex; white-space: nowrap; align-items: center; gap: 14px; '
            'background: linear-gradient(165deg, #4E3C31 0%, #2B211C 100%); color: #F6F0E8; '
            'text-decoration: none; font-weight: 700; font-size: clamp(18px, 1.9vw, 22px); '
            'letter-spacing: .01em; padding: 23px 34px 23px 48px; border-radius: 999px; '
            'box-shadow: 0 16px 34px -12px rgba(43,33,28,.55), 0 0 0 1px rgba(43,33,28,.9), '
            '0 0 0 8px rgba(201,168,127,.22), inset 0 1px 0 rgba(255,255,255,.14); '
            'transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;" '
            'style-hover="transform: translateY(-3px); filter: brightness(1.08);" '
            'style-active="transform: translateY(-1px);">Попасть в предзапись'
            '<span style="display: inline-flex; align-items: center; justify-content: center; '
            'width: 34px; height: 34px; border-radius: 50%; '
            'background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; '
            'font-size: 16px; line-height: 1;">→</span></a>')

EYEBROW = ('font-size: 12px; letter-spacing: .18em; text-transform: uppercase; '
           'color: #8A5A2B;')

ICON_DIAMOND = ('<span style="display: inline-flex; align-items: center; justify-content: center; '
                'width: 26px; height: 26px; margin-top: 2px; border-radius: 50%; '
                'background: linear-gradient(160deg, #F0DCBB, #C29A6C); color: #2A211C; '
                'font-size: 13px; line-height: 1; flex: none;">◆</span>')

ICON_GIFT = ('<span style="display: inline-flex; align-items: center; justify-content: center; '
             'width: 30px; height: 30px; margin-top: 1px; border-radius: 50%; '
             'background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; '
             'flex: none;"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
             'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><path d="M4 11h16v9.5H4z"/>'
             '<path d="M2.8 7.5h18.4V11H2.8zM12 7.5v13"/>'
             '<path d="M12 7.5S10.7 4 8.4 4a1.9 1.9 0 0 0 0 3.5zM12 7.5S13.3 4 15.6 4'
             'a1.9 1.9 0 0 1 0 3.5z"/></svg></span>')

# Порядок пунктов не тот, что был в присланном тексте: закрытый канал поднят
# на первое место. Он единственный, что человек получает сегодня же; цена
# и разговор с командой работают только если он вообще решит покупать.
PRE_FOR_REQUEST = [
    ("Закрытый канал Виолы",
     "подкасты и материалы, которых нет в открытом доступе. Новое вы видите там первыми."),
    ("Вход по самой низкой цене",
     "она закрепляется за вами до 4&nbsp;сентября."),
    ("Право сказать, что включить в программу",
     "в канале спросим, чего вам не хватает, и соберём из ваших ответов часть программы."),
    ("Разговор с командой Виолы Маро",
     "расскажут, как устроен практикум, какой тариф под вашу задачу, ответят на вопросы "
     "и помогут с оплатой, в том числе в рассрочку."),
]

PRE_FOR_EARLY = [
    ("«Любовь и деньги»",
     "лекция Виолы о том, почему и любовь, и деньги про одно и то же состояние наполненности."),
    ("Разбор фильма «Догвиль»",
     "как эмпат оказывается в позиции жертвы, как устроена эмоциональная зависимость "
     "и как из неё выходят."),
    ("Большой мастер-класс на узнавание себя",
     "там подробно разобрано то, что тест показал коротко."),
]





# ─────────────────────────────────────────────── экраны страницы брони ──

BOOKING_GIVES = [
    ("Место на потоке",
     "оно закрепляется за вами и не уходит другому, пока идёт набор."),
    ("Цена не изменится",
     "сколько бы ни стоило участие к старту, вы платите по цене, "
     "зафиксированной сегодня."),
    ("Все бонусы остаются вашими",
     "включая те, что действуют только для ранней оплаты."),
]


def booking_screens():
    """Короткая страница под личную отправку.

    Продавать заново незачем: человек уже поговорил с командой и решает
    вносить бронь. Поэтому экранов с программой здесь нет, только условия
    и кнопка.
    """
    rows = "".join(
        '<div style="background: linear-gradient(180deg, #FFFFFF 0%%, #FDFAF6 100%%); '
        'border: 1px solid #E9DFD2; border-radius: 16px; '
        'box-shadow: 0 1px 2px rgba(60,48,40,.04), 0 16px 36px -24px rgba(60,48,40,.34); '
        'padding: clamp(24px, 3vw, 32px); display: flex; flex-direction: column; gap: 12px;">'
        '<span style="display: inline-flex; align-items: center; justify-content: center; '
        'width: 44px; height: 44px; border-radius: 50%%; '
        'background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; '
        'font-size: 18px; font-weight: 700; flex: none; '
        'box-shadow: inset 0 1px 0 rgba(255,255,255,.5);">%d</span>'
        '<h3 style="margin: 0; font-size: clamp(19px, 2.1vw, 23px); font-weight: 700; '
        'letter-spacing: -.02em; line-height: 1.25; color: #2E2521;">%s</h3>'
        '<p style="margin: 0; font-size: 17px; line-height: 1.55; color: #5C5149;">%s</p>'
        "</div>" % (i + 1, t, tail)
        for i, (t, tail) in enumerate(BOOKING_GIVES))

    return '''
<div id="bron" data-screen-label="06 Что даёт бронь" style="background: linear-gradient(180deg, #F5EFE6 0%%, #EFE6DA 100%%); padding: clamp(56px, 8vw, 100px) clamp(14px, 4vw, 40px);">
  <div style="max-width: 1020px; margin: 0 auto; display: flex; flex-direction: column; gap: clamp(26px, 3.4vw, 38px);">
    <div style="display: flex; flex-direction: column; gap: 12px; align-items: center; text-align: center;">
      <div style="%(eyebrow)s">Что даёт бронь</div>
      <h2 style="font-family: \'Golos Text\', system-ui, sans-serif; font-weight: 700; letter-spacing: -.025em; font-size: clamp(34px, 5vw, 56px); line-height: 1.1; margin: 0; text-wrap: balance;">Три вещи, которые бронь закрепляет за&nbsp;вами</h2>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; align-items: stretch;">%(rows)s</div>

    <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 20px 32px; background: linear-gradient(165deg, #4A392F 0%%, #2B211C 100%%); border: 1px solid #33271F; border-radius: 18px; box-shadow: 0 22px 48px -26px rgba(43,33,28,.75), inset 0 1px 0 rgba(255,255,255,.1); padding: clamp(26px, 3.4vw, 38px);">
      <div style="flex: 0 0 auto; display: flex; flex-direction: column; gap: 4px;">
        <span style="font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: #E9C98F;">Размер брони</span>
        <span style="font-size: clamp(40px, 6vw, 60px); font-weight: 700; letter-spacing: -.03em; line-height: 1; color: #F6F0E8;">%(amount)s</span>
      </div>
      <div style="flex: 1 1 300px; display: flex; flex-direction: column; gap: 10px; font-size: 17.5px; line-height: 1.55; color: #DCD1C4;">
        <p style="margin: 0;"><b style="color: #F6F0E8; font-weight: 700;">Засчитывается в&nbsp;стоимость участия.</b> Это не&nbsp;доплата сверху: остаток вы&nbsp;вносите за&nbsp;вычетом брони.</p>
        <p style="margin: 0;">Остаток&nbsp;— до&nbsp;%(deadline)s, дня старта потока.</p>
      </div>
    </div>

    <div style="display: flex; flex-direction: column; gap: 10px; max-width: 68ch; align-self: center; text-align: center;">
      <p style="margin: 0; font-size: 17px; line-height: 1.55; color: #2E2521;">%(carry)s</p>
    </div>

    %(cta)s
  </div>
</div>
''' % {"eyebrow": EYEBROW, "rows": rows, "cta": CTA_BOOK,
       "amount": BOOKING_AMOUNT, "deadline": BOOKING_DEADLINE,
       "carry": BOOKING_CARRY}


def gifts_block():
    """Подарки за раннюю оплату — в шапку формы оплаты.

    Человек видит их в момент, когда решает платить, а не страницей выше,
    где он их уже пролистал. Список тот же, что на странице предзаписи:
    расходиться этим двум местам нельзя.
    """
    rows = "".join(
        '<div style="display: grid; grid-template-columns: auto 1fr; gap: 12px; '
        'align-items: start;">%s<p style="margin: 0; font-size: 16px; line-height: 1.5; '
        'color: #DCD1C4;"><b style="color: #F6F0E8; font-weight: 700;">%s</b>&nbsp;— %s</p>'
        "</div>" % (ICON_GIFT, t, tail)
        for t, tail in PRE_FOR_EARLY)

    return ('<div style="display: flex; flex-direction: column; gap: 13px; margin-top: 4px; '
            'padding-top: 18px; border-top: 1px solid rgba(246,240,232,.16);">'
            '<div style="font-size: 12px; letter-spacing: .18em; text-transform: uppercase; '
            'color: #E9C98F;">За раннюю оплату</div>'
            + rows + "</div>")


ICON_TG = ('<span style="display: inline-flex; align-items: center; justify-content: center; '
           'width: 40px; height: 40px; border-radius: 50%; '
           'background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; '
           'font-size: 18px; line-height: 1; flex: none;">\u2708</span>')


def care_rows():
    """Две строки-ссылки: имя, юзернейм, стрелка. Вся строка кликабельна.

    Юзернейм вынесен отдельной строкой и крупным: с телефона его не выделишь
    из текста, а искать вручную никто не станет — поэтому он должен читаться
    и как подпись, и как цель нажатия.
    """
    строки = []
    for i, (имя, ник, url) in enumerate(CARE_ACCOUNTS):
        рамка = "" if i == 0 else "border-top: 1px solid #EFE6DA; "
        строки.append(
            '<a href="' + url + '" target="_blank" rel="noopener" '
            'style="' + рамка + 'display: grid; grid-template-columns: auto 1fr auto; '
            'gap: 14px; align-items: center; padding: 16px 2px; text-decoration: none; '
            'color: inherit;">'
            + ICON_TG +
            '<span style="display: flex; flex-direction: column; gap: 3px; min-width: 0;">'
            '<span style="font-size: 18px; font-weight: 600; line-height: 1.25; '
            'color: #2E2521;">' + имя + '</span>'
            '<span style="font-size: 16.5px; line-height: 1.3; color: #6B4E2C; '
            'overflow-wrap: anywhere;">' + ник + '</span>'
            '</span>'
            '<span aria-hidden="true" style="display: inline-flex; align-items: center; '
            'justify-content: center; width: 34px; height: 34px; border-radius: 50%; '
            'background: rgba(42,33,28,.9); color: #F0DCBB; font-size: 16px; '
            'line-height: 1; flex: none;">\u2192</span>'
            '</a>')
    return "".join(строки)


def contacts_screen():
    """Экран «Задать вопрос команде» — одна полоса на два контакта.

    Стоит перед финальным призывом: человек дочитал, решение ещё не принято,
    и здесь ему дают живого человека вместо кнопки покупки. В подвале
    контакт тоже есть, но подвал не читают.
    """
    return ('\n<div id="kontakty" data-screen-label="10 Контакты команды" '
            'style="background: linear-gradient(180deg, #FFFFFF 0%, #FBF6EF 100%); '
            'border-top: 1px solid #E4DACD; '
            'padding: clamp(48px, 6.5vw, 84px) clamp(14px, 4vw, 40px);">'
            '<div style="max-width: 720px; margin: 0 auto; '
            'background: linear-gradient(180deg, #FFFFFF 0%, #FDFAF6 100%); '
            'border: 1px solid #DCCFBC; border-radius: 16px; '
            'box-shadow: 0 1px 2px rgba(60,48,40,.05), 0 18px 40px -24px rgba(60,48,40,.34); '
            'padding: clamp(22px, 3.2vw, 32px); display: flex; flex-direction: column; '
            'gap: 16px;">'
            '<div style="display: flex; flex-direction: column; gap: 8px;">'
            '<div style="' + EYEBROW + '">Отдел заботы</div>'
            '<h2 style="margin: 0; font-family: \'Golos Text\', system-ui, sans-serif; '
            'font-weight: 700; letter-spacing: -.025em; font-size: clamp(26px, 3.6vw, 40px); '
            'line-height: 1.12; color: #2E2521; text-wrap: balance;">'
            'Задать вопрос команде</h2>'
            '</div>'
            '<div style="display: flex; flex-direction: column;">' + care_rows() + '</div>'
            '<p style="margin: 0; font-size: 16.5px; line-height: 1.5; color: #2E2521; '
            'font-weight: 600;">' + CARE_ONLY + '</p>'
            '<p style="margin: 0; font-size: 15px; line-height: 1.5; color: #7D7167;">'
            + CARE_HOURS + '</p>'
            '</div></div>\n')


def care_note(размер="15px"):
    """Та же мысль одной строкой — для мест, где целый экран не нужен:
    под тарифами и в форме заявки."""
    ссылки = " · ".join(
        '<a href="' + url + '" target="_blank" rel="noopener" '
        'style="color: #6B4E2C; font-weight: 600;">' + ник + '</a>'
        for _имя, ник, url in CARE_ACCOUNTS)
    return ('<p style="margin: 0; font-size: ' + размер + '; line-height: 1.5; '
            'color: #5C5149;"><b style="color: #2E2521;">' + CARE_ONLY + '</b> '
            + ссылки + '</p>')


def pre_benefits_screen():
    """«Что даёт предзапись» — экран, на котором принимается решение.

    Два яруса нарочно разной плотности: за заявку — светлый, порог нулевой;
    за раннюю оплату — тёмный с бронзой, единственное цветное пятно экрана.
    Разница между ними должна читаться до чтения текста.

    Срок назван словами и один раз. Ни таймера, ни счётчика мест: прямая
    красная линия проекта, правка эксперта была «целевая аудитория получается
    каких-то обиженных и оскорблённых».
    """
    def row(title, tail, icon, title_color, text_color):
        return ('<div style="display: grid; grid-template-columns: auto 1fr; gap: 14px; '
                'align-items: start;">%s<p style="margin: 0; font-size: 17.5px; '
                'line-height: 1.55; color: %s;"><b style="color: %s; font-weight: 700;">%s</b>'
                '&nbsp;— %s</p></div>' % (icon, text_color, title_color, title, tail))

    light = "".join(row(t, x, ICON_DIAMOND, "#2E2521", "#5C5149") for t, x in PRE_FOR_REQUEST)
    dark = "".join(row(t, x, ICON_GIFT, "#F6F0E8", "#DCD1C4") for t, x in PRE_FOR_EARLY)

    return '''
<div id="zapis" data-screen-label="06 Что даёт предзапись" style="background: linear-gradient(180deg, #F5EFE6 0%%, #EFE6DA 100%%); padding: clamp(56px, 8vw, 100px) clamp(14px, 4vw, 40px);">
  <div style="max-width: 1020px; margin: 0 auto; display: flex; flex-direction: column; gap: clamp(26px, 3.4vw, 38px);">
    <div style="display: flex; flex-direction: column; gap: 12px; align-items: center; text-align: center;">
      <div style="%(eyebrow)s">Пока идёт набор</div>
      <h2 style="font-family: 'Golos Text', system-ui, sans-serif; font-weight: 700; letter-spacing: -.025em; font-size: clamp(38px, 5.6vw, 64px); line-height: 1.1; margin: 0; text-wrap: balance;">Что даёт предзапись</h2>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; align-items: stretch;">

      <div style="background: linear-gradient(180deg, #FFFFFF 0%%, #FDFAF6 100%%); border: 1px solid #E9DFD2; border-radius: 16px; box-shadow: 0 1px 2px rgba(60,48,40,.04), 0 16px 36px -24px rgba(60,48,40,.34); padding: clamp(24px, 3.4vw, 36px); display: flex; flex-direction: column; gap: 18px;">
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <div style="%(eyebrow)s">За саму заявку</div>
          <p style="margin: 0; font-size: 19px; font-weight: 600; line-height: 1.35; color: #2E2521;">Ничего платить не&nbsp;нужно</p>
        </div>
        <div style="display: flex; flex-direction: column; gap: 14px;">%(light)s</div>
      </div>

      <div style="background: linear-gradient(165deg, #4A392F 0%%, #2B211C 100%%); border: 1px solid #33271F; border-radius: 16px; box-shadow: 0 20px 44px -24px rgba(43,33,28,.7), inset 0 1px 0 rgba(255,255,255,.1); padding: clamp(24px, 3.4vw, 36px); display: flex; flex-direction: column; gap: 18px;">
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <div style="font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: #E9C98F;">За раннюю оплату</div>
          <p style="margin: 0; font-size: 19px; font-weight: 600; line-height: 1.35; color: #F6F0E8;">Три подарка сверх программы</p>
        </div>
        <div style="display: flex; flex-direction: column; gap: 14px;">%(dark)s</div>
      </div>

    </div>

    <div style="align-self: center; max-width: 54ch; text-align: center; display: flex; flex-direction: column; gap: 8px;">
      <p style="margin: 0; font-size: 17px; line-height: 1.55; color: #2E2521;">Оплату оформляет команда: после заявки она свяжется с&nbsp;вами.</p>
      <p style="margin: 0; font-size: 17px; line-height: 1.55; color: #5C5149;">С 5&nbsp;сентября цена становится выше.</p>
    </div>

    %(cta)s
  </div>
</div>
''' % {"eyebrow": EYEBROW, "light": light, "dark": dark, "cta": CTA_DARK,
}


# Состав участия сгруппирован, а не вывален списком из тринадцати галок.
# Четыре группы человек охватывает взглядом; тринадцать равных строк —
# читает по диагонали и не запоминает ни одной.
PRE_GROUPS = [
    ("Программа",
     '<rect x="3" y="4.5" width="18" height="13" rx="1.6"/>'
     '<path d="M8 21h8M12 17.5V21M10.6 8.6l4.4 2.6-4.4 2.6z"/>',
     ["Шесть лекций Виолы в прямом эфире, по одной в неделю",
      "18 техник эмпата, по три на неделю",
      "Практическое задание после каждой лекции"]),
    ("Внимание Виолы",
     '<rect x="9" y="3" width="6" height="10" rx="3"/>'
     '<path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
     ["Вопрос Виоле на аудиоразбор каждую неделю",
      "Вопросы и ответы в конце лекции",
      "Мастер-класс в прямом эфире с ответами Виолы",
      "Участие в финальной встрече"]),
    ("Материалы",
     '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9.5 12h5M9.5 16h5"/>',
     ["Запись и PDF-конспект к каждой лекции",
      "Разбор вас как эмпата, личный PDF",
      "Большая методичка по итогам потока",
      "Аудиомедитация на изобилие"]),
    ("Люди рядом",
     '<circle cx="9" cy="9" r="3"/><circle cx="16.5" cy="12" r="2.4"/>'
     '<path d="M3.5 19c.7-2.8 2.8-4.3 5.5-4.3M13 19c.3-1.9 1.6-2.9 3.5-2.9s3.2 1 3.5 2.9"/>',
     ["Группа до двадцати человек",
      "Чат потока"]),
]


def pre_contents_screen():
    """«Что входит в практикум» — четыре карточки вместо списка из галок.

    Тарифы намеренно не показываются: на предзаписи цены нет, а выбор тарифа
    человек делает в разговоре с командой. Показывать урезанный состав раньше
    времени значит отговаривать на пустом месте.
    """
    def card(title, paths, items):
        icon = ('<span style="display: inline-flex; align-items: center; justify-content: center; '
                'width: 46px; height: 46px; border-radius: 50%%; '
                'background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; '
                'flex: none; box-shadow: inset 0 1px 0 rgba(255,255,255,.5);">'
                '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" '
                'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
                'aria-hidden="true">%s</svg></span>' % paths)
        rows = "".join(
            '<div style="display: grid; grid-template-columns: 9px 1fr; gap: 12px; '
            'align-items: start;"><span style="width: 5px; height: 5px; margin-top: 10px; '
            'border-radius: 50%%; background: #C9A87F;"></span>'
            '<span style="font-size: 17px; line-height: 1.5; color: #5C5149;">%s</span></div>' % t
            for t in items)
        return ('<div style="background: linear-gradient(180deg, #FFFFFF 0%%, #FDFAF6 100%%); '
                'border: 1px solid #E9DFD2; border-radius: 16px; '
                'box-shadow: 0 1px 2px rgba(60,48,40,.04), 0 16px 36px -24px rgba(60,48,40,.34); '
                'padding: clamp(24px, 3vw, 32px); display: flex; flex-direction: column; '
                'gap: 16px;">%s<h3 style="margin: 0; font-size: clamp(20px, 2.2vw, 24px); '
                'font-weight: 700; letter-spacing: -.02em; line-height: 1.25; color: #2E2521;">'
                '%s</h3><div style="display: flex; flex-direction: column; gap: 11px;">%s</div>'
                "</div>" % (icon, title, rows))

    cards = "".join(card(t, p, i) for t, p, i in PRE_GROUPS)

    return '''
<div data-screen-label="07 Что входит" style="background: linear-gradient(180deg, #FBF7F1 0%%, #F4EDE3 100%%); padding: clamp(56px, 8vw, 100px) clamp(14px, 4vw, 40px);">
  <div style="max-width: 1020px; margin: 0 auto; display: flex; flex-direction: column; gap: clamp(24px, 3vw, 34px);">
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <div style="%(eyebrow)s">По максимуму</div>
      <h2 style="font-family: \'Golos Text\', system-ui, sans-serif; font-weight: 700; letter-spacing: -.025em; font-size: clamp(38px, 5.6vw, 64px); line-height: 1.1; margin: 0; text-wrap: balance;">Что входит в практикум</h2>
      <p style="margin: 0; font-size: clamp(17.1px, 1.89vw, 19.8px); line-height: 1.55; max-width: 60ch; color: #5C5149;">Полный состав участия&nbsp;— всё, что можно получить на&nbsp;практикуме.</p>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 18px; align-items: stretch;">%(cards)s</div>

    <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 16px 22px; background: linear-gradient(165deg, #4A392F 0%%, #2B211C 100%%); border: 1px solid #33271F; border-radius: 16px; box-shadow: 0 18px 40px -24px rgba(43,33,28,.7), inset 0 1px 0 rgba(255,255,255,.1); padding: clamp(22px, 3vw, 28px) clamp(24px, 3vw, 32px);">
      <span style="display: inline-flex; align-items: center; justify-content: center; width: 52px; height: 52px; border-radius: 50%%; background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; font-size: 24px; font-weight: 700; flex: none; box-shadow: inset 0 1px 0 rgba(255,255,255,.5);">∞</span>
      <div style="flex: 1 1 260px; display: flex; flex-direction: column; gap: 4px;">
        <p style="margin: 0; font-size: clamp(19px, 2.1vw, 23px); font-weight: 700; letter-spacing: -.02em; color: #F6F0E8;">Доступ навсегда</p>
        <p style="margin: 0; font-size: 17px; line-height: 1.5; color: #DCD1C4;">Записи, конспекты и&nbsp;материалы остаются у&nbsp;вас без срока.</p>
      </div>
    </div>

    <p style="margin: 0; font-size: 17px; line-height: 1.55; color: #5C5149;">Тарифы и&nbsp;цены команда разберёт с&nbsp;вами лично: подскажет, какой тариф под&nbsp;вашу задачу, и&nbsp;поможет оформить оплату, в&nbsp;том числе в&nbsp;рассрочку.</p>

    %(cta)s
  </div>
</div>
''' % {"eyebrow": EYEBROW, "cards": cards, "cta": CTA_DARK}



TIMER_SCREEN = """
<div data-screen-label="01b Срок предзаписи" id="srok" style="background: linear-gradient(180deg, #2B211C 0%, #241C18 100%); border-top: 1px solid rgba(246,240,232,.12); padding: clamp(20px, 3vw, 30px) clamp(14px, 4vw, 40px);">
  <div style="max-width: 1020px; margin: 0 auto; display: flex; flex-direction: column; align-items: center; text-align: center; gap: clamp(12px, 2vw, 16px);">
    <p style="margin: 0; max-width: 34ch; font-size: clamp(15px, 1.7vw, 17px); font-weight: 700; line-height: 1.4; color: #F6F0E8;">До&nbsp;конца подарков за&nbsp;раннюю оплату</p>
    <div id="countdown" style="display: flex; align-items: flex-start; gap: clamp(10px, 2vw, 18px);" data-deadline="__DEADLINE__">
      <div style="display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 54px;"><span data-cd="d" style="font-size: clamp(26px, 4vw, 34px); font-weight: 700; letter-spacing: -.02em; line-height: 1; color: #F0DCBB; font-variant-numeric: tabular-nums;">—</span><span style="font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #B8AA9C;">дней</span></div>
      <div style="display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 54px;"><span data-cd="h" style="font-size: clamp(26px, 4vw, 34px); font-weight: 700; letter-spacing: -.02em; line-height: 1; color: #F0DCBB; font-variant-numeric: tabular-nums;">—</span><span style="font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #B8AA9C;">часов</span></div>
      <div style="display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 54px;"><span data-cd="m" style="font-size: clamp(26px, 4vw, 34px); font-weight: 700; letter-spacing: -.02em; line-height: 1; color: #F0DCBB; font-variant-numeric: tabular-nums;">—</span><span style="font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #B8AA9C;">минут</span></div>
      <div style="display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 54px;"><span data-cd="s" style="font-size: clamp(26px, 4vw, 34px); font-weight: 700; letter-spacing: -.02em; line-height: 1; color: #C9A87F; font-variant-numeric: tabular-nums;">—</span><span style="font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: #B8AA9C;">секунд</span></div>
    </div>
  </div>
</div>
""".replace("__DEADLINE__", GIFT_ISO)


# ──────────────────────────────────────────────────────────────── лендинг ──

def build_landing():
    raw = read(os.path.join(SRC, "Лендинг ПЭ 4.0.dc.html"))
    tpl = raw[raw.index("</helmet>") + len("</helmet>"):]
    tpl = tpl[:tpl.index('<script type="text/x-dc"')]

    tpl = expand_weeks(tpl)

    # ── первый экран: image-slot → <picture> ────────────────────────────────
    tpl = re.sub(
        r'<div data-hero-photo="" style="[^"]*">.*?</div>',
        lambda m: '<div data-hero-photo="" style="position: absolute; inset: 0;">\n        '
                  + hero_picture() + "\n      </div>",
        tpl, count=1, flags=re.S)

    # ── модальная форма: React-состояние → обычный <dialog>-подобный блок ──
    blk = find_block(tpl, "sc-if")            # первый оставшийся sc-if — это formOpen
    o, bs, be, ce = blk
    form = tpl[bs:be]

    for cond, el_id in (("formError", "form-error"), ("formSent", "form-sent")):
        inner = find_block(form, "sc-if")
        io, ibs, ibe, ice = inner
        body = form[ibs:ibe].strip()
        body = re.sub(r"^<(\w+)", r'<\1 id="%s" hidden' % el_id, body, count=1)
        form = form[:io] + body + form[ice:]

    form = form.replace("{{ formPlan }}", '<span id="form-plan"></span>')
    form = form.replace("{{ formError }}", '<span id="form-error-text"></span>')
    form = re.sub(r'\sonClick="\{\{ closeForm \}\}"', ' data-close-form', form)
    form = re.sub(r'\sonClick="\{\{ submitForm \}\}"', ' id="form-submit"', form)

    fields = {"fName": ("name", "text"), "fPhone": ("phone", "tel"), "fTg": ("tg", "text")}
    for var, (nm, _t) in fields.items():
        form = re.sub(r'\svalue="\{\{ %s \}\}"\s*onInput="\{\{ on\w+ \}\}"' % var,
                      ' name="%s"' % nm, form)

    boxes = {"agreeOffer": ("accept_offer", True), "agreeData": ("accept_pd", True),
             "agreeMail": ("accept_ads", False)}
    for var, (nm, req) in boxes.items():
        form = re.sub(r'\schecked="\{\{ %s \}\}"\s*onChange="\{\{ \w+ \}\}"' % var,
                      ' name="%s"%s' % (nm, " required" if req else ""), form)

    # ссылки на документы вместо href="#"
    doc_links = iter(["/offer", "/offer-prilozhenie", "/consent", "/privacy", "/consent-ads"])
    n_hrefs = form.count('href="#"')
    if n_hrefs != 5:
        raise ValueError("в форме ожидалось 5 ссылок-заглушек, найдено %d" % n_hrefs)
    form = re.sub(r'href="#"',
                  lambda m: 'href="%s" target="_blank" rel="noopener"' % next(doc_links), form)

    # сообщение об ошибке рядом с каждой обязательной галкой (требование правового ТЗ)
    must = ('<span style="font-size: 12px; letter-spacing: .14em; text-transform: uppercase; '
            'color: #8A5A2B;">Обязательно</span>')
    if form.count(must) != 2:
        raise ValueError("ожидалось две обязательные галки, найдено %d" % form.count(must))
    form = form.replace(must, must + '<span class="cb-err" hidden></span>')

    # ── это не заявка, а шаг перед оплатой ────────────────────────────────
    # Контакты и согласия собираются здесь, потому что акцепт оферты должен
    # быть получен и записан до платежа (раздел 3 правового ТЗ). Сразу после
    # записи в таблицу человек уходит на страницу оплаты.
    note = 'style="margin: 0; font-size: 15px; line-height: 1.5; color: #7D7167;"'

    # Исходные подписи шаблона описывают ровно сценарий заявки: человек
    # оставляет контакты, дальше пишет команда. В режиме zayavka их почти
    # не нужно трогать — а вот платёжные, наоборот, все до одной лишние.
    IS_ZAYAVKA = MODE == "zayavka"

    for old, new in () if IS_ZAYAVKA else (
        ("Запись на поток",
         "Оформление участия"),
        ("Оставьте контакты&nbsp;— мы напишем вам",
         "Оставьте контакты&nbsp;— на&nbsp;них придут доступы"),
        ("Ответим в&nbsp;Telegram, поможем оформить оплату или рассрочку.",
         "Дальше откроется страница оплаты. Заплатить можно целиком или частями."),
        ("Отправить заявку",
         "Перейти к оплате"),
        ("Готово. Мы получили заявку и&nbsp;напишем вам в&nbsp;Telegram.",
         "Готово. Открываем страницу оплаты…"),
    ):
        if old not in form:
            raise ValueError("не найдена строка модалки: %s" % old)
        form = form.replace(old, new)

    tail = "Нажимая кнопку, вы&nbsp;подтверждаете отмеченные согласия.</p>"

    if IS_ZAYAVKA:
        # Оплаты на странице нет, значит нет и акцепта оферты: требовать
        # согласие с договором купли-продажи там, где ничего не покупают,
        # юридически неверно и просто лишний барьер. Так же сделано
        # на предзаписи.
        form = drop_field(form, "accept_offer")

        for old, new in (
            ("Запись на поток", "Заявка на участие"),
            ("Оставьте контакты&nbsp;— мы напишем вам",
             "Оставьте контакты&nbsp;— команда напишет вам"),
            ("Ответим в&nbsp;Telegram, поможем оформить оплату или рассрочку.",
             "Сразу после заявки откроется чат с&nbsp;командой Виолы "
             "в&nbsp;Telegram: расскажем, как устроен практикум, ответим "
             "на&nbsp;вопросы и&nbsp;поможем провести оплату безопасно&nbsp;— "
             "целиком или в&nbsp;рассрочку."),
            ("Готово. Мы получили заявку и&nbsp;напишем вам в&nbsp;Telegram.",
             "Готово. Открываем чат с&nbsp;командой…"),
        ):
            if old not in form:
                raise ValueError("не найдена строка модалки заявки: %s" % old)
            form = form.replace(old, new)

        form = form.replace(tail, tail
            + "<p %s>Заявка ничего не&nbsp;списывает и&nbsp;ни&nbsp;к&nbsp;чему "
              "не&nbsp;обязывает: тариф и&nbsp;способ оплаты вы&nbsp;обсудите "
              "с&nbsp;командой.</p>" % note
            + "<p %s>Оплата и&nbsp;чек&nbsp;— от&nbsp;ИП Нижевясова А.&nbsp;С., "
              "продюсера программ Виолы Маро.</p>" % note)
    else:
        form = form.replace(tail, tail
            + "<p %s>Оплата и&nbsp;чек&nbsp;— от&nbsp;ИП Нижевясова А.&nbsp;С., "
              "продюсера программ Виолы Маро.</p>" % note
            + "<p %s>Также вам напишет команда Виолы, если у&nbsp;вас не&nbsp;получится, "
              "и&nbsp;поможет найти варианты оплаты, если вы&nbsp;точно решили идти "
              "на&nbsp;программу.</p>" % note
            + "<p %s>После оплаты вам сразу же напишут из&nbsp;команды Виолы, чтобы выдать "
              "все доступы и&nbsp;показать, как всё работает, чтобы вы&nbsp;с&nbsp;максимальным "
              "комфортом прошли программу.</p>" % note)

    if MODE == "bron":
        # Деньги принимаются, значит акцепт оферты обязателен — галка
        # остаётся, в отличие от предзаписи.
        for old, new in (
            ("Оформление участия", "Бронь места"),
            ("Оставьте контакты&nbsp;— на&nbsp;них придут доступы",
             "Оставьте контакты&nbsp;— пришлём доступы"),
            ("Дальше откроется страница оплаты. Заплатить можно целиком или частями.",
             "Дальше откроется оплата брони %s. Она засчитывается в&nbsp;стоимость "
             "участия, остаток вносится до&nbsp;%s." % (BOOKING_AMOUNT, BOOKING_DEADLINE)),
            ("Перейти к оплате", "Внести бронь " + BOOKING_AMOUNT),
        ):
            if old not in form:
                raise ValueError("не найдена строка модалки брони: %s" % old)
            form = form.replace(old, new)

    if MODE == "pre":
        # Предзаписи нечего акцептовать: покупки нет, значит нет и оферты.
        # Требовать её согласие на бесплатной заявке юридически неверно
        # и лишний барьер. Согласие на обработку ПД остаётся — контакты
        # мы всё равно собираем.
        form = drop_field(form, "accept_offer")

        chip = re.search(r'<div style="display: inline-flex; align-self: flex-start;[^>]*>'
                         r'.*?</div>\s*</div>', form, re.S)
        if chip:
            form = form[:chip.start()] + "</div>" + form[chip.end():]

        for old, new in (
            ("Оформление участия", "Предзапись"),
            ("Оставьте контакты&nbsp;— на&nbsp;них придут доступы",
             "Оставьте контакты&nbsp;— откроем канал"),
            ("Дальше откроется страница оплаты. Заплатить можно целиком или частями.",
             "Сразу после заявки откроется закрытый канал Виолы. Команда свяжется с&nbsp;вами "
             "в&nbsp;Telegram: расскажет, как устроен практикум, ответит на&nbsp;вопросы "
             "и&nbsp;поможет оформить оплату."),
            ("Перейти к оплате", "Попасть в предзапись"),
            ("Готово. Открываем страницу оплаты…", "Готово. Открываем закрытый канал…"),
        ):
            if old not in form:
                raise ValueError("не найдена строка модалки предзаписи: %s" % old)
            form = form.replace(old, new)

        # вопрос о готовности — между контактами и согласиями
        opts = ("Готов(а) участвовать", "Присматриваюсь", "Пока не готов(а), но интересно")
        radios = "".join(
            '<label style="display: grid; grid-template-columns: 26px 1fr; gap: 14px; '
            'align-items: center; cursor: pointer;">'
            '<input type="radio" name="readiness" value="%s"%s style="appearance: auto; '
            'width: 20px; height: 20px; margin: 0; accent-color: #4A392F; cursor: pointer;">'
            '<span style="font-size: 16.5px; line-height: 1.45; color: #3B2E28;">%s</span>'
            "</label>" % (o, " checked" if i == 0 else "", o)
            for i, o in enumerate(opts))
        block = ('<div style="display: flex; flex-direction: column; gap: 12px;">'
                 '<span style="font-size: 13px; font-weight: 600; letter-spacing: .16em; '
                 'text-transform: uppercase; color: #6B4E2C;">Готовность пойти на программу'
                 "</span>" + radios + "</div>")
        divider = ('<div style="height: 1px; background: linear-gradient(90deg, #C9A87F, '
                   'rgba(228,218,205,.2));"></div>')
        form = form.replace(divider, block + divider, 1)

        # подписи под кнопкой у предзаписи свои: платить пока нечего
        keep = "Нажимая кнопку, вы&nbsp;подтверждаете отмеченные согласия.</p>"
        tail = form.index(keep) + len(keep)
        form = form[:tail] + ('<p style="margin: 0; font-size: 15px; line-height: 1.5; '
                              'color: #7D7167;">Заявка бесплатна и&nbsp;ни&nbsp;к&nbsp;чему '
                              'не&nbsp;обязывает.</p>') + form[form.index("</div>", tail):]

    # Кому писать и с каких аккаунтов ждать ответа — там, где человек
    # оставляет свой Telegram. Вставляется после правок всех режимов:
    # у предзаписи свой блок приписок затирает всё, что стоит раньше.
    маркер = "Нажимая кнопку, вы&nbsp;подтверждаете отмеченные согласия.</p>"
    if маркер not in form:
        raise ValueError("не найдена приписка под кнопкой формы")
    form = form.replace(маркер, маркер + care_note(), 1)

    # приманка для ботов: поле не видно и не читается экранным диктором,
    # заполнить его может только робот, который разбирает форму по разметке
    honeypot = ('<div class="hp" aria-hidden="true">'
                '<label>Не заполняйте это поле'
                '<input type="text" name="website" tabindex="-1" autocomplete="off">'
                "</label></div>")
    form = form.replace('<label style="display: flex; flex-direction: column; gap: 8px;">',
                        honeypot + '<label style="display: flex; flex-direction: column; gap: 8px;">', 1)

    if MODE in ("pay", "bron", "zayavka"):
        # Подарки идут под плашкой тарифа, внутри тёмной шапки формы:
        # это последний экран перед платежом, и здесь они ещё работают.
        # После id="form-plan" идут два </span> и </div> самой плашки:
        # первый же </div> и есть её закрытие. Следующий закрыл бы тёмную
        # шапку, и блок оказался бы под карточкой, на голой подложке.
        i = form.index('id="form-plan"')
        j = form.index("</div>", i) + len("</div>")
        form = form[:j] + gifts_block() + form[j:]

    # Чем кончается отправка: страница оплаты, закрытый канал или
    # ничего — заявку разбирает команда.
    after = {"pre": "channel", "zayavka": "team"}.get(MODE, "pay")
    form = ('<div id="lead-modal" class="modal" role="dialog" aria-modal="true" '
            'aria-labelledby="lead-title" data-after="%s" hidden>' % after + form + "</div>")
    form = form.replace('<h2 style="margin: 0; font-family:', '<h2 id="lead-title" style="margin: 0; font-family:', 1)
    tpl = tpl[:o] + form + tpl[ce:]

    # ── кнопки тарифов открывают форму ─────────────────────────────────────
    # Ссылка на оплату одна на тариф: и прямая оплата, и рассрочка ведут
    # на неё же — способ человек выбирает уже на стороне GetPlatinum.
    # Кнопка при этом помнит, что именно нажали: это уходит в таблицу.
    plans = {"openBasicPay": ("Самостоятельный — оплата целиком", "basic"),
             "openBasicInst": ("Самостоятельный — в рассрочку", "basic"),
             "openFullPay": ("С Виолой — оплата целиком", "full"),
             "openFullInst": ("С Виолой — в рассрочку", "full")}
    for var, (label, key) in plans.items():
        tpl = tpl.replace('onClick="{{ %s }}"' % var,
                          'data-open-form="%s" data-pay="%s"' % (label, key))

    # «Оформить рассрочку» ведёт к тарифам, а не в поддержку: рассрочка
    # оформляется на той же странице оплаты, что и прямой платёж, но сначала
    # человек должен выбрать тариф. Заодно снимаем target="_blank" —
    # это якорь на своей же странице, новая вкладка тут ни к чему.
    inst = re.search(r'<a href="\{\{ contactUrl \}\}"[^>]*>', tpl)
    if not inst:
        raise ValueError("не найдена кнопка «Оформить рассрочку»")
    fixed = (inst.group(0)
             .replace('href="{{ contactUrl }}"', 'href="#tarify"')
             .replace(' target="_blank"', '')
             .replace(' rel="noopener"', ''))
    tpl = tpl[:inst.start()] + fixed + tpl[inst.end():]

    tpl = tpl.replace("{{ contact }}", TG)

    # День недели убран: расписание эфиров может сдвинуться, а обещание
    # с сайта останется — и человек придёт в четверг к пустому эфиру.
    # Доступ навсегда остаётся: это про сам продукт, а не про календарь.
    # \u00a0 — неразрывные пробелы из исходника, обычные тут не совпадут
    четверг = "Лекции идут по\u00a0четвергам. Доступ ко\u00a0всему остаётся навсегда."
    if четверг not in tpl:
        raise ValueError("не найдена строка про день лекций")
    tpl = tpl.replace(четверг, "Доступ ко\u00a0всему остаётся навсегда.")

    # <br> внутри h1 не даёт пробела при копировании и в выдаче
    tpl = tpl.replace("Прикладная<br>эмпатия", "Прикладная <br>эмпатия", 1)

    # надзаголовок первого экрана: имя не должно разрываться по строкам
    tpl = tpl.replace("от\u00a0Виолы Маро", "от\u00a0Виолы\u00a0Маро")

    if MODE == "bron":
        # Страницу отправляют лично тем, кто уже поговорил с командой.
        # Продавать заново незачем — остаются только первый экран,
        # условия брони и призыв.
        for label in ("02 Зачем мне это", "03 Что нового", "04 Программа шесть недель",
                      "05 Финальный мастер-класс", "06 Тарифы",
                      "06b Проблемы с оплатой", "07 Рассрочка"):
            tpl = drop_screen(tpl, label)

        tpl = insert_before_screen(tpl, "11 Финальный призыв", booking_screens())

        tpl = tpl.replace("Принять участие", "Внести бронь")
        tpl = tpl.replace('href="#tarify"',
                          'href="#bron" data-open-form="Бронь места" data-pay="bron"')

        tpl = tpl.replace("от 14&nbsp;900&nbsp;₽", "Бронь " + BOOKING_AMOUNT)
        tpl = tpl.replace(
            "В «С Виолой» пятьдесят мест. Оплатить можно сразу или частями&nbsp;— "
            "рассрочка до&nbsp;12&nbsp;месяцев для&nbsp;СНГ.",
            "Бронь %s закрепляет за&nbsp;вами место, цену и&nbsp;бонусы. "
            "Остаток&nbsp;— до&nbsp;%s." % (BOOKING_AMOUNT, BOOKING_DEADLINE))
        tpl = tpl.replace("Цена предзаписи действует до&nbsp;4&nbsp;сентября",
                          "Бронь засчитывается в&nbsp;стоимость участия")

        # Заголовок прямо называет, что это за страница.
        tpl = tpl.replace("Прикладная <br>эмпатия",
                          "Бронь на <br>«Прикладную эмпатию»", 1)

    if MODE == "pre":
        # Уходят все экраны, где есть цена или оплата. Рассрочка тоже: она
        # про деньги, а её содержание сжимается в одну строку про разговор
        # с командой в блоке «что входит».
        for label in ("06 Тарифы", "06b Проблемы с оплатой", "07 Рассрочка"):
            tpl = drop_screen(tpl, label)

        tpl = insert_before_screen(tpl, "11 Финальный призыв",
                                   pre_benefits_screen() + pre_contents_screen())

        # Срок — сразу под первым экраном, тонкой полосой.
        tpl = insert_before_screen(tpl, "02 Зачем мне это", TIMER_SCREEN)

        # Надзаголовок: первым словом «Предзапись», плашкой, чтобы читалось
        # раньше названия. Дальше — что это за практикум, мелким.
        old_brow = ('<div style="font-size: clamp(10px, 1.7vw, 12.5px); letter-spacing: .2em; '
                    'text-transform: uppercase; color: #C9A87F; line-height: 1.5;">'
                    '6-недельный практикум для\u00a0эмпатов от\u00a0Виолы\u00a0Маро</div>')
        if old_brow not in tpl:
            raise ValueError("не найден надзаголовок первого экрана")
        tpl = tpl.replace(old_brow,
            '<div style="display: flex; align-items: center; flex-wrap: wrap; gap: 10px 12px; '
            'font-size: clamp(10px, 1.7vw, 12.5px); letter-spacing: .2em; '
            'text-transform: uppercase; color: #C9A87F; line-height: 1.5;">'
            '<b style="background: linear-gradient(180deg, #F0DCBB, #C29A6C); color: #2A211C; '
            'font-weight: 700; letter-spacing: .16em; padding: 7px 14px; border-radius: 999px; '
            'box-shadow: inset 0 1px 0 rgba(255,255,255,.5);">Предзапись</b>'
            '<span>на 6-недельный практикум для\u00a0эмпатов от\u00a0Виолы\u00a0Маро</span>'
            "</div>")

        # Один призыв на все кнопки, как и было в исходном брифе: этой
        # аудитории не надо гадать, куда нажимать.
        tpl = tpl.replace("Принять участие", "Попасть в предзапись")

        # Кнопки вели к тарифам, которых больше нет. Теперь открывают форму,
        # а якорь остаётся запасным путём, если скрипт не отработал.
        tpl = tpl.replace('href="#tarify"',
                          'href="#zapis" data-open-form="Предзапись"')

        # Липкая панель: вместо цены — состояние набора.
        tpl = tpl.replace("от 14&nbsp;900&nbsp;₽", "Предзапись открыта")
        tpl = tpl.replace(
            '<span style="font-size: 17px; font-weight: 600; color: #2E2521;">',
            '<span style="font-size: 16px; font-weight: 700; color: #2E2521;">', 1)

        # Финальный экран говорил про оплату и цену — обоих пока нет.
        tpl = tpl.replace(
            "В «С Виолой» пятьдесят мест. Оплатить можно сразу или частями&nbsp;— "
            "рассрочка до&nbsp;12&nbsp;месяцев для&nbsp;СНГ.",
            "Предзапись открыта. Цена закрепляется за&nbsp;вами до&nbsp;4&nbsp;сентября, "
            "дальше она выше.")
        tpl = tpl.replace("Цена предзаписи действует до&nbsp;4&nbsp;сентября",
                          "Заявка бесплатна и&nbsp;ни&nbsp;к&nbsp;чему не&nbsp;обязывает")

    if MODE == "zayavka":
        # Страницу отправляют тем, кто пришёл из канала и часто платит
        # онлайн впервые. Цены остаются на месте — уходит только сам
        # платёж: кнопки открывают заявку, а оплату человек проводит
        # вместе с командой. Это и есть смысл страницы: не оставить
        # человека один на один с платёжной формой.
        for old, new, expect in (
            ("Принять участие", "Оставить заявку", 7),
            (">Оплатить", ">Оставить заявку", 2),
            (">В рассрочку", ">Хочу в рассрочку", 2),
        ):
            if tpl.count(old) != expect:
                raise ValueError("кнопка %s: ожидалось %d, найдено %d"
                                 % (old, expect, tpl.count(old)))
            tpl = tpl.replace(old, new)

        tpl = tpl.replace(
            "В «С Виолой» пятьдесят мест. Оплатить можно сразу или частями&nbsp;— "
            "рассрочка до&nbsp;12&nbsp;месяцев для&nbsp;СНГ.",
            "В «С Виолой» пятьдесят мест. Оставьте заявку&nbsp;— откроется чат "
            "с&nbsp;командой: ответим на&nbsp;вопросы и&nbsp;поможем оплатить безопасно.")

        # Липкая панель обещала переход к оплате — теперь ведёт к заявке.
        tpl = tpl.replace("Цена предзаписи действует до&nbsp;4&nbsp;сентября",
                          "Оплату проводим вместе с&nbsp;командой")

    # Контакты команды — отдельным экраном перед финальным призывом,
    # на всех четырёх версиях страницы.
    tpl = insert_before_screen(tpl, "11 Финальный призыв", contacts_screen())

    if MODE in ("pay", "zayavka"):
        # Та же мысль под тарифами: это момент, когда человек решается
        # платить, и именно тогда полезно знать, кто ему напишет.
        курс = ('<p style="margin: 0; font-size: 16px;">Цены в&nbsp;долларах '
                'и&nbsp;евро справочные: оплата идёт в&nbsp;рублях по&nbsp;курсу '
                'на&nbsp;день оплаты.</p>')
        if курс not in tpl:
            raise ValueError("не найдена сноска о курсе под тарифами")
        tpl = tpl.replace(курс, курс + care_note("16px"), 1)

    # ── сноска про Meta у самого упоминания (требование правового ТЗ) ──────
    # На странице брони экран с этим упоминанием не выводится, и сноска
    # вместе с ним не нужна: ставить её не к чему.
    mentions = tpl.count("Инстаграме")
    if mentions > 1:
        raise ValueError("ожидалось одно упоминание Инстаграма, найдено %d" % mentions)
    HAS_META_NOTE = mentions == 1
    tpl = tpl.replace("Инстаграме",
                      'Инстаграме<a href="#meta-note" class="fn" '
                      'aria-label="Сноска: Meta признана экстремистской организацией в России">*</a>')

    # ── подвал .dc заменяем на правовой ────────────────────────────────────
    m = re.search(r'<div data-screen-label="12 Подвал"', tpl)
    tpl = tpl[:m.start()]

    tpl = fix_contrast(tpl)
    tpl = divs_to_sections(tpl)
    tpl = collect_state_styles(tpl)

    body = ('<main id="main">' + tpl.strip() + "</main>" + footer_html() + COOKIE_HTML)

    # Предзагрузки нет намеренно: <link rel="preload" as="image"> не умеет
    # выбирать между <source> по типу и тянет JPEG поверх уже выбранного WebP —
    # лишние 100 КБ на первом экране. Портрет и так первый элемент в DOM,
    # сканер предзагрузки находит его сразу, а приоритет задан fetchpriority.
    extra = ""

    page = head(
        "Прикладная эмпатия — 6-недельный практикум Виолы Маро",
        "Шесть недель, шесть сфер жизни и 18 техник для людей с повышенной чувствительностью. "
        "Практикум психолога Виолы Маро. Старт 1 октября.",
        "/assets/site.css", extra)
    page += body
    page += '\n<script src="/assets/site.js"></script>\n</body>\n</html>\n'
    write(os.path.join(OUT, "index.html"), page)
    return page


# ──────────────────────────────────────────────── страница «Неудобные» ──
#
# Собирается не из шаблона DesignCraft, а из своей разметки: у события
# нет ни недель, ни тарифов, ни формы заявки, и натягивать на него
# лендинг практикума значило бы тащить десять чужих экранов ради двух
# общих. Общими остаются шапка, подвал, cookie-полоса, шрифты и палитра —
# то, что обязано совпадать на всех страницах сайта.


CTA_NEUD = ('<a class="n-btn n-cta" href="#bilet">Приобрести билет'
            '<span class="n-arrow" aria-hidden="true">→</span></a>')


# Обратный отсчёт и липкая панель. В исходнике DesignCraft это состояние
# компонента; здесь то же самое обычным скриптом, без сборки и зависимостей.
#
# Дата стоит в двух местах: здесь и в тексте страницы («до 4 сентября»).
# Меняете срок — меняете оба.
NEUD_JS = """
(function () {
  'use strict';

  var box = document.querySelector('[data-timer]');
  if (box) {
    var end = new Date(2026, 8, 4, 23, 59, 59);
    var cells = {};
    ['d', 'dl', 'h', 'hl', 'm', 'ml'].forEach(function (k) {
      cells[k] = box.querySelector('[data-cd="' + k + '"]');
    });
    var plural = function (n, forms) {
      var a = Math.abs(n) % 100, b = a % 10;
      if (a > 10 && a < 20) return forms[2];
      if (b === 1) return forms[0];
      if (b >= 2 && b <= 4) return forms[1];
      return forms[2];
    };
    var timer;
    var tick = function () {
      var ms = end - new Date();
      /* Срок вышел — полоса убирается целиком. Нули читаются как сломанная
         страница, а подарок к этому моменту и правда закрыт. */
      if (ms <= 0) { box.hidden = true; clearInterval(timer); return; }
      var d = Math.floor(ms / 86400000),
          h = Math.floor(ms / 3600000) % 24,
          m = Math.floor(ms / 60000) % 60;
      cells.d.textContent = d; cells.dl.textContent = plural(d, ['день', 'дня', 'дней']);
      cells.h.textContent = h; cells.hl.textContent = plural(h, ['час', 'часа', 'часов']);
      cells.m.textContent = m; cells.ml.textContent = plural(m, ['минута', 'минуты', 'минут']);
    };
    tick();
    timer = setInterval(tick, 30000);
  }

  var bar = document.querySelector('[data-sticky]');
  if (bar) {
    var on = null;
    var scroll = function () {
      var v = window.scrollY > window.innerHeight * 0.9 ? '1' : '0';
      if (v !== on) { on = v; bar.setAttribute('data-on', v); }
    };
    window.addEventListener('scroll', scroll, { passive: true });
    scroll();
  }
})();
"""

# Стиль лендинга приходит из исходника, а не из build-assets. Заполняется
# в build_neudobnye(), поэтому build_css() обязан идти после сборки страницы.
NEUD_CSS = ""


def build_neudobnye():
    """Страница события. Собирается из исходника DesignCraft.

    Лендинг полностью переработан заказчиком 31.08: своя палитра
    с терракотовым акцентом, засечная Literata, счётчик мест и обратный
    отсчёт. К прежней версии страницы отношения не имеет, поэтому
    build-assets/neudobnye.html и neudobnye.css сняты.

    Сборщик делает четыре вещи и больше ничего: вынимает стиль и разметку,
    снимает внешние ссылки на шрифты, разворачивает шаблонные подстановки
    в обычный скрипт и подставляет настоящие адреса картинок и оплаты.
    Вёрстку заказчика не трогает: правки по ней идут отдельно и осознанно,
    иначе следующий экспорт из DesignCraft их затрёт.
    """
    global NEUD_CSS
    raw = read(os.path.join(SRC, "Лендинг Неудобные v5.dc.html"))

    NEUD_CSS = re.search(r"<style>(.*?)</style>", raw, re.S).group(1).strip()
    # Константы неиспользуемых картинок: объявлены, нигде не читаются.
    NEUD_CSS = re.sub(r'\s*--foto-(geroy|avtor):\s*url\("[^"]*"\);', "", NEUD_CSS)

    body = raw[raw.index("</helmet>") + len("</helmet>"):]
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    body = body[:body.index("</x-dc>")]
    body = re.sub(r"</?x-dc[^>]*>", "", body).strip()

    # ── подстановки шаблона → разметка под обычный скрипт ──────────────
    for mark, cell in (("dd", "d"), ("hh", "h"), ("mm", "m"),
                       ("ddLabel", "dl"), ("hhLabel", "hl"), ("mmLabel", "ml")):
        token = "{{ %s }}" % mark
        if token not in body:
            raise ValueError("в исходнике нет метки %s" % token)
        body = body.replace(token, '<span data-cd="%s">—</span>' % cell)
    body = body.replace('data-on="{{ sticky }}"', 'data-on="0"')

    left = re.findall(r"\{\{[^}]*\}\}", body)
    if left:
        raise ValueError("остались нераскрытые подстановки: %s" % left[:3])

    # ── портрет первого экрана ─────────────────────────────────────────
    if body.count('<img data-geroy="1"') != 1:
        raise ValueError("ожидался один портрет первого экрана")
    body = re.sub(r'<img data-geroy="1"[^>]*>', lambda _m: geroy_picture(), body, count=1)

    # ── портрет автора ─────────────────────────────────────────────────
    if body.count('<img data-avtor="1"') != 1:
        raise ValueError("ожидался один портрет автора")
    body = re.sub(r'<img data-avtor="1"[^>]*>', lambda _m: avtor_picture(), body, count=1)

    # ── кнопки открывают форму, а не ведут сразу на оплату ─────────────
    #
    # Так же, как на странице практикума: контакты и согласия собираются
    # до платежа, потому что акцепт оферты должен быть получен и записан
    # раньше денег (раздел 3 правового ТЗ). Сразу после записи в таблицу
    # человек уходит на страницу оплаты.
    n_btn = body.count('data-btn="1" href="#"')
    if n_btn < 3:
        raise ValueError("ожидалось не меньше трёх кнопок оплаты, найдено %d" % n_btn)
    body = body.replace('data-btn="1" href="#"',
                        'data-btn="1" href="#zapis" data-open-form="Неудобные" '
                        'data-pay="neudobnye"')

    form = read(os.path.join(BUILD_ASSETS, "neudobnye-form.html")).strip()

    page = head(
        "Неудобные. Терапевтический уикенд Виолы Маро 11–13 сентября",
        "Три дня 11–13 сентября: лекция о жизненных ролях, авторская медитация "
        "и прямой эфир с Виолой Маро. Записи остаются навсегда. 3 500 ₽ до 4 сентября.",
        "/assets/site.css")
    page += '<main id="main">\n' + body + "\n</main>\n"
    page += form + "\n"
    page += footer_html() + COOKIE_HTML
    page += '\n<script src="/assets/site.js"></script>\n</body>\n</html>\n'
    write(os.path.join(OUT, "index.html"), page)

    print("  index.html: страница события «Неудобные», исходник v5")
    print("  форма заявки: %d кнопки «Занять место» открывают её" % n_btn)
    return page


# ────────────────────────────────────────────────────────── правовые страницы ──

def build_docs():
    for slug, url, title in DOCS:
        frag = read(os.path.join(LEGAL, slug + ".html"))

        # первый заголовок становится <h1> страницы и убирается из текста
        m = re.search(r"<h([12])[^>]*>(.*?)</h\1>", frag, re.S)
        heading = re.sub(r"\s+", " ", re.sub("<[^>]+>", "", m.group(2))).strip()
        frag = frag[:m.start()] + frag[m.end():]

        # таблицы — со скроллом внутри своего контейнера
        frag = re.sub(r"<table", '<div class="tw"><table', frag)
        frag = re.sub(r"</table>", "</table></div>", frag)

        # cookie-полоса ссылается на /privacy#cookie — даём разделу короткий якорь
        frag = re.sub(r'(<h[1-6] id="[^"]*cookie[^"]*")',
                      r'<span id="cookie" class="anchor"></span>\1', frag, count=1)

        page = head(heading + " — Прикладная эмпатия",
                    "%s. ИП Нижевясова А. С., организатор программ Виолы Маро." % heading,
                    "/assets/site.css")
        page += """
<header class="doc-top">
  <div class="doc-top-in">
    <a class="doc-back" href="/">← Прикладная эмпатия</a>
  </div>
</header>
<main id="main" class="doc">
  <div class="doc-in">
    <h1>%s</h1>
    %s
  </div>
</main>
""" % (html_mod.escape(heading), frag.strip())
        page += footer_html() + COOKIE_HTML
        page += '\n<script src="/assets/site.js"></script>\n</body>\n</html>\n'
        write(os.path.join(OUT, url, "index.html"), page)
        print("  /%s — %s" % (url, heading))


# ───────────────────────────────────────────────────────────────── шрифты ──

FONT_FACES = [
    ("Golos Text", "GolosText-cyrillic-ext.woff2", "400 700",
     "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F"),
    ("Golos Text", "GolosText-cyrillic.woff2", "400 700",
     "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116"),
    ("Golos Text", "GolosText-latin-ext.woff2", "400 700",
     "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF"),
    ("Golos Text", "GolosText-latin.woff2", "400 700",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
    ("Prata", "Prata-cyrillic-ext.woff2", "400",
     "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F"),
    ("Prata", "Prata-cyrillic.woff2", "400",
     "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116"),
    ("Prata", "Prata-latin.woff2", "400",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
]


# Literata — засечный шрифт нового лендинга события. У остальных страниц
# сайта его нет, поэтому список отдельный: в общий FONT_FACES он попадать
# не должен, иначе практикум начнёт таскать 250 КБ, которых не использует.
#
# Начертания сняты с Google Fonts и подшиты файлами. Исходник события
# грузил их ссылкой, а на этом сайте внешних запросов не бывает ни одного:
# страница обязана открываться из России без VPN, ради этого из лендинга
# практикума в своё время убрали ровно такую же ссылку.
LITERATA_FACES = [
    ("Literata", "Literata-cyrillic-ext-400-italic.woff2", "400", "italic",
     "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F"),
    ("Literata", "Literata-cyrillic-400-italic.woff2", "400", "italic",
     "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116"),
    ("Literata", "Literata-latin-ext-400-italic.woff2", "400", "italic",
     "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF"),
    ("Literata", "Literata-latin-400-italic.woff2", "400", "italic",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
    ("Literata", "Literata-cyrillic-ext-400.woff2", "400", "normal",
     "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F"),
    ("Literata", "Literata-cyrillic-400.woff2", "400", "normal",
     "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116"),
    ("Literata", "Literata-latin-ext-400.woff2", "400", "normal",
     "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF"),
    ("Literata", "Literata-latin-400.woff2", "400", "normal",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
    ("Literata", "Literata-cyrillic-ext-600.woff2", "600", "normal",
     "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F"),
    ("Literata", "Literata-cyrillic-600.woff2", "600", "normal",
     "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116"),
    ("Literata", "Literata-latin-ext-600.woff2", "600", "normal",
     "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF"),
    ("Literata", "Literata-latin-600.woff2", "600", "normal",
     "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD"),
]


def font_css():
    out = []
    for fam, fname, weight, urange in FONT_FACES:
        out.append(
            "@font-face{font-family:'%s';font-style:normal;font-weight:%s;font-display:swap;"
            "src:url(/assets/fonts/%s) format('woff2');unicode-range:%s}"
            % (fam, weight, fname, urange))
    for fam, fname, weight, style, urange in (LITERATA_FACES if MODE == "neudobnye" else []):
        out.append(
            "@font-face{font-family:'%s';font-style:%s;font-weight:%s;font-display:swap;"
            "src:url(/assets/fonts/%s) format('woff2');unicode-range:%s}"
            % (fam, style, weight, fname, urange))
    return "\n".join(out)


def copy_fonts():
    dst = os.path.join(OUT, "assets", "fonts")
    os.makedirs(dst, exist_ok=True)
    total = 0
    names = [f[1] for f in FONT_FACES]
    if MODE == "neudobnye":
        names += [f[1] for f in LITERATA_FACES]
    for fname in names:
        s = os.path.join(BUILD_ASSETS, "fonts", fname)
        shutil.copy2(s, os.path.join(dst, fname))
        total += os.path.getsize(s)
    print("  шрифты: %d файлов, %.0f КБ" % (len(names), total / 1024))


# ──────────────────────────────────────────────────────────────────── CSS ──

def build_css():
    css = font_css() + "\n\n" + read(os.path.join(BUILD_ASSETS, "base.css"))
    if MODE == "neudobnye":
        css += "\n\n/* ── событие «Неудобные», стиль из исходника ── */\n" + NEUD_CSS
    css += "\n\n/* состояния наведения и фокуса, перенесённые из инлайновых стилей */\n"
    css += hover_css() + "\n"
    write(os.path.join(OUT, "assets", "site.css"), css)
    print("  site.css: %.0f КБ" % (len(css.encode()) / 1024))


def build_js():
    js = read(os.path.join(BUILD_ASSETS, "site.js")) + "\n" + COOKIE_JS
    if MODE == "neudobnye":
        js += "\n" + NEUD_JS
    write(os.path.join(OUT, "assets", "site.js"), js)


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#2B211C"/>
  <text x="32" y="45" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif"
        font-size="38" fill="#E4C08A">Э</text>
</svg>
"""


def build_favicon():
    write(os.path.join(OUT, "assets", "favicon.svg"), FAVICON)


# ──────────────────────────────────────────────────── версии файлов ──
#
# Имена картинок и стилей не меняются от сборки к сборке, поэтому браузер
# продолжает показывать сохранённую копию — новое фото до человека просто
# не доезжает. К каждой ссылке на файл дописывается короткий хеш его
# содержимого: меняется файл — меняется адрес — кэш обновляется сам.

def add_cache_busting():
    digests = {}
    missing = set()

    def digest(rel):
        if rel not in digests:
            path = os.path.join(OUT, rel.lstrip("/"))
            if not os.path.isfile(path):
                return None
            with open(path, "rb") as f:
                digests[rel] = hashlib.md5(f.read()).hexdigest()[:8]
        return digests[rel]

    ref = re.compile(r"/assets/[\w./-]+\.(?:css|js|webp|jpg|png|svg)")

    def stamp(m):
        rel = m.group(0)
        if BASE and rel.startswith(BASE):
            rel = rel[len(BASE):]
        d = digest(rel)
        if d is None:
            missing.add(rel)          # файла нет — это битая ссылка, не мелочь
            return m.group(0)
        return "%s?v=%s" % (m.group(0), d)

    n = 0
    for dirpath, _dirs, files in os.walk(OUT):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as f:
                html = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(ref.sub(stamp, html))
            n += 1
    if missing:
        raise ValueError("страницы ссылаются на несуществующие файлы: %s"
                         % ", ".join(sorted(missing)))
    print("  версии файлов проставлены в %d страницах" % n)


# ──────────────────────────────────────────────── сборка под Тильду ──
#
# Тильда даёт вставить произвольный HTML в блок T123, но страница вокруг
# уже своя: свои стили, свои шрифты, свой контейнер. Поэтому кусок для
# вставки готовится иначе, чем обычная страница.
#
# Три отличия:
#   1. Стили ограничены обёрткой .vm — иначе правила на body, html и *
#      уедут в вёрстку Тильды, а её правила придут в нашу.
#   2. Шрифты и картинки зашиты в сам кусок: путей /assets на Тильде нет.
#   3. Ни <html>, ни <head> — только содержимое. Заголовок страницы
#      и описание заводятся в настройках страницы Тильды.

TILDA_SCOPE = "vm"

VM_WIDTH_JS = """
/* Точная ширина окна без полосы прокрутки — для выхода блока на всю ширину
   изнутри контейнера Тильды. 100vw для этого не годится: она полосу считает. */
(function () {
  var root = document.documentElement;
  function set() { root.style.setProperty('--vm-vw', root.clientWidth + 'px'); }
  set();
  addEventListener('resize', set);
  addEventListener('orientationchange', function () { setTimeout(set, 250); });
})();
"""


def _data_uri(path, mime):
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


def _scope_css(css, scope):
    """Приписывает каждому селектору обёртку.

    Правила на html и body становятся правилами на саму обёртку: внутри
    Тильды у нас нет своего body, его роль играет .vm.
    """
    out = []
    i = 0
    while i < len(css):
        if css[i] == "@":
            # @font-face и @media: первый оставляем как есть, во второй заходим
            head_end = css.index("{", i)
            at = css[i:head_end].strip()
            depth, j = 1, head_end + 1
            while depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            body = css[head_end + 1:j - 1]
            if at.startswith("@media") or at.startswith("@supports"):
                out.append("%s{%s}" % (at, _scope_css(body, scope)))
            else:
                out.append("%s{%s}" % (at, body))
            i = j
            continue

        brace = css.find("{", i)
        if brace == -1:
            break
        close = css.index("}", brace)
        sels = css[i:brace].strip()
        decls = css[brace + 1:close].strip()
        i = close + 1
        if not sels:
            continue

        fixed = []
        for sel in sels.split(","):
            sel = sel.strip()
            if not sel:
                continue
            if sel in ("html", "body"):
                fixed.append("." + scope)
            elif sel.startswith("body."):
                fixed.append(".%s%s" % (scope, sel[4:]))
            elif sel.startswith("html "):
                fixed.append(".%s %s" % (scope, sel[5:]))
            elif sel.startswith("*"):
                fixed.append(".%s%s" % (scope, sel[1:]))
                fixed.append(".%s *%s" % (scope, sel[1:]))
            else:
                fixed.append(".%s %s" % (scope, sel))
        out.append("%s{%s}" % (",".join(fixed), decls))
    return "".join(out)


def build_tilda(src_dir, out_dir):
    """Из готовых страниц делает куски для вставки в блок T123."""
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    css = read(os.path.join(src_dir, "assets", "site.css"))
    js = read(os.path.join(src_dir, "assets", "site.js"))

    # шрифты внутрь стилей
    fonts = 0
    for name in sorted(os.listdir(os.path.join(src_dir, "assets", "fonts"))):
        uri = _data_uri(os.path.join(src_dir, "assets", "fonts", name), "font/woff2")
        css = css.replace("url(/assets/fonts/%s)" % name, "url(%s)" % uri)
        fonts += 1

    css = _scope_css(css, TILDA_SCOPE)

    # Блок Тильды может лежать внутри её колонки с ограниченной шириной,
    # и тогда первый экран получает поля по бокам вместо края в край.
    # Приём стандартный: растянуть обёртку на ширину окна и вытянуть её
    # назад отрицательным отступом. Если блок и так во всю ширину,
    # отступ выходит нулевым и ничего не меняется.
    # Правило идёт последним намеренно: body{margin:0} из общих стилей
    # превращается в .vm{margin:0} и обнулило бы отрицательный отступ,
    # стой оно после. Ширина берётся не из 100vw — эта единица считает
    # и полосу прокрутки, давая лишний горизонтальный скролл; точную
    # ширину без полосы подставляет скрипт.
    css = css + (".%s{width:var(--vm-vw,100vw);max-width:var(--vm-vw,100vw);"
                 "margin-left:calc(50%% - var(--vm-vw,100vw)/2);}" % TILDA_SCOPE)

    made = []
    for dirpath, _dirs, files in os.walk(src_dir):
        if "index.html" not in files:
            continue
        rel = os.path.relpath(dirpath, src_dir)
        html = read(os.path.join(dirpath, "index.html"))

        body = html[html.index("<body>") + len("<body>"):html.rindex("</body>")]
        body = re.sub(r'<a class="skip".*?</a>\s*', "", body, flags=re.S)
        body = re.sub(r'<script src="[^"]*"></script>\s*', "", body)

        # Внутрь куска идёт только WebP и только по одному размеру на кадр:
        # JPEG-запаска и мелкие варианты удваивали вес, а base64 и так
        # раздувает файл на треть. WebP понимают все браузеры с 2020 года.
        pic = re.search(r"<picture>.*?</picture>", body, re.S)
        if pic:
            body = body[:pic.start()] + (
                '<picture>'
                '<source media="(max-width: 760px)" type="image/webp" '
                'srcset="/assets/img/hero-mob.webp">'
                '<img src="/assets/img/hero.webp" '
                'alt="Виола Маро сидит в кресле" width="1672" height="941" '
                'fetchpriority="high" decoding="async">'
                '</picture>') + body[pic.end():]

        # картинки внутрь разметки
        def inline(m):
            path = os.path.join(src_dir, m.group(1).lstrip("/").split("?")[0])
            if not os.path.isfile(path):
                return m.group(0)
            mime = "image/webp" if path.endswith(".webp") else "image/jpeg"
            return m.group(0).replace(m.group(1), _data_uri(path, mime))

        body = re.sub(r'(/assets/img/[\w.-]+(?:\?v=[a-f0-9]+)?)', inline, body)

        name = ("index" if rel == "." else rel.replace(os.sep, "-")) + ".html"
        piece = ("<style>" + css + "</style>\n"
                 + '<div class="' + TILDA_SCOPE + '">' + body.strip() + "</div>\n"
                 + "<script>" + VM_WIDTH_JS + js + "</script>\n")
        write(os.path.join(out_dir, name), piece)
        made.append((name, os.path.getsize(os.path.join(out_dir, name)) / 1024))

    print("  куски для Тильды (%d шрифтов внутри):" % fonts)
    for name, kb in sorted(made):
        print("    %-26s %6.0f КБ" % (name, kb))


# ─────────────────────────────────────────────────────────────────── main ──

def parse_args(argv):
    global BASE, NOINDEX, MODE, OUT, DOCS_ROOT, CNAME, TILDA_OUT
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mode":
            i += 1
            MODE = argv[i]
            if MODE not in ("pay", "pre", "bron", "zayavka", "neudobnye"):
                sys.exit("режим бывает pay, pre, bron, zayavka или neudobnye, "
                         "получено: %s" % MODE)
        elif a == "--out":
            i += 1
            OUT = os.path.join(ROOT, argv[i])
        elif a == "--base":
            i += 1
            BASE = "/" + argv[i].strip("/")
        elif a.startswith("--base="):
            BASE = "/" + a.split("=", 1)[1].strip("/")
        elif a == "--docs-root":
            DOCS_ROOT = True
        elif a == "--cname":
            i += 1
            CNAME = argv[i]
        elif a == "--tilda":
            i += 1
            TILDA_OUT = argv[i]
        elif a == "--noindex":
            NOINDEX = True
        else:
            sys.exit("неизвестный аргумент: %s" % a)
        i += 1


def main():
    parse_args(sys.argv[1:])
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    print("Сборка сайта → %s  (режим: %s)" % (os.path.relpath(OUT, ROOT), MODE))
    if BASE:
        print("  подпуть: %s" % BASE)
    if NOINDEX:
        print("  индексация запрещена")
    copy_fonts()
    if MODE == "neudobnye":
        build_geroy_photo()
        build_avtor_photo()
        build_neudobnye()
    else:
        build_images()
        build_landing()      # заполняет HOVER_RULES
    if DOCS_ROOT:
        print("  правовые страницы не строятся: ссылки ведут в корень домена")
    else:
        build_docs()
    build_css()              # поэтому идёт после
    build_js()
    build_favicon()
    if CNAME:
        write(os.path.join(OUT, "CNAME"), CNAME + "\n")
        print("  CNAME → %s" % CNAME)
    add_cache_busting()

    if TILDA_OUT:
        build_tilda(OUT, os.path.join(ROOT, TILDA_OUT))

    total = 0
    for dirpath, _dirs, files in os.walk(OUT):
        for f in files:
            total += os.path.getsize(os.path.join(dirpath, f))
    print("Готово. Всего %.0f КБ" % (total / 1024))


if __name__ == "__main__":
    main()
