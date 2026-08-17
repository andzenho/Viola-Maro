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

TG = "https://t.me/violamarohelper"
EMAIL = "mg.ananizh@gmail.com"

# Вертикальный портрет из той же съёмки — исходник первого экрана на телефоне.
MOBILE_SRC = "ChatGPT Image 15 авг. 2026 г., 07_55_58.png"

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

ABS_ROOTS = ["assets/"] + [url for _s, url, _t in DOCS]


def apply_base(text):
    """Проставляет префикс подпути всем корневым адресам в готовой странице."""
    if not BASE:
        return text
    text = text.replace('href="/"', 'href="%s/"' % BASE)
    for root in ABS_ROOTS:
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
        <a href="%(tg)s" target="_blank" rel="noopener">@violamarohelper</a>
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
""" % {"email": EMAIL, "tg": TG, "docs": docs}


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
    from PIL import Image, ImageFilter
    src = os.path.join(SRC, "assets", "viola-hero.png")
    outdir = os.path.join(OUT, "assets", "img")
    os.makedirs(outdir, exist_ok=True)
    im = Image.open(src).convert("RGB")
    W, H = im.size

    def save(img, name, widths):
        for w in widths:
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
                p = os.path.join(outdir, "%s-%d.%s" % (name, w, ext))
                r.save(p, **kw)
                made.append(p)

    made = []
    # десктоп — исходный горизонтальный кадр
    save(im, "hero", (1672, 1200))

    # Телефон берёт другой исходник — вертикальный портрет из той же съёмки.
    # Он и по композиции нужный (Виола справа, слева пустой фон под текст),
    # и по разрешению заметно больше горизонтального: 1086×1448 против
    # кропа 853×941, который приходилось растягивать на высокий экран.
    vert = Image.open(os.path.join(SRC, "uploads", MOBILE_SRC)).convert("RGB")
    vw, vh = vert.size

    # Кадр всё равно шире экрана телефона по пропорции, поэтому надставляется
    # сверху: верхняя строка фотографии — ровный тёмный градиент без деталей,
    # её и растягиваем вверх с затуханием. Шов приходится на неё же и не виден.
    #
    # Размер надставки задаёт вертикаль. Текст стоит двумя блоками — шапка
    # сверху, обещание с кнопкой снизу, — между ними свободная полоса, и лицо
    # должно попасть в неё. 80 px дают голову с 23%, подбородок на 46%.
    ext_h = 80
    row0 = vert.crop((0, 0, vw, 1))
    top = Image.new("RGB", (vw, ext_h))
    for i in range(ext_h):
        k = 0.72 + 0.28 * (i / (ext_h - 1))     # 0.72 наверху → ровно 1.0 на шве
        top.paste(row0.point(lambda v, k=k: int(v * k)), (0, i))
    mob = Image.new("RGB", (vw, vh + ext_h))
    mob.paste(top, (0, 0))
    mob.paste(vert, (0, ext_h))

    save(mob, "hero-mob", (vw, 760))

    total = sum(os.path.getsize(p) for p in made)
    print("  картинки: %d файлов, %.0f КБ" % (len(made), total / 1024))


HERO_PICTURE = """<picture>
          <source media="(max-width: 760px)" type="image/webp"
                  srcset="/assets/img/hero-mob-760.webp 760w, /assets/img/hero-mob-1086.webp 1086w"
                  sizes="100vw">
          <source media="(max-width: 760px)" type="image/jpeg"
                  srcset="/assets/img/hero-mob-760.jpg 760w, /assets/img/hero-mob-1086.jpg 1086w"
                  sizes="100vw">
          <source type="image/webp"
                  srcset="/assets/img/hero-1200.webp 1200w, /assets/img/hero-1672.webp 1672w"
                  sizes="100vw">
          <img src="/assets/img/hero-1672.jpg"
               srcset="/assets/img/hero-1200.jpg 1200w, /assets/img/hero-1672.jpg 1672w"
               sizes="100vw"
               alt="Виола Маро сидит в кресле"
               width="1672" height="941"
               fetchpriority="high" decoding="async">
        </picture>"""


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
                  + HERO_PICTURE + "\n      </div>",
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

    # приманка для ботов: поле не видно и не читается экранным диктором,
    # заполнить его может только робот, который разбирает форму по разметке
    honeypot = ('<div class="hp" aria-hidden="true">'
                '<label>Не заполняйте это поле'
                '<input type="text" name="website" tabindex="-1" autocomplete="off">'
                "</label></div>")
    form = form.replace('<label style="display: flex; flex-direction: column; gap: 8px;">',
                        honeypot + '<label style="display: flex; flex-direction: column; gap: 8px;">', 1)

    form = ('<div id="lead-modal" class="modal" role="dialog" aria-modal="true" '
            'aria-labelledby="lead-title" hidden>' + form + "</div>")
    form = form.replace('<h2 style="margin: 0; font-family:', '<h2 id="lead-title" style="margin: 0; font-family:', 1)
    tpl = tpl[:o] + form + tpl[ce:]

    # ── кнопки тарифов открывают форму ─────────────────────────────────────
    plans = {"openBasicPay": "Самостоятельный — оплата целиком",
             "openBasicInst": "Самостоятельный — в рассрочку",
             "openFullPay": "С Виолой — оплата целиком",
             "openFullInst": "С Виолой — в рассрочку"}
    for var, label in plans.items():
        tpl = tpl.replace('onClick="{{ %s }}"' % var, 'data-open-form="%s"' % label)

    tpl = tpl.replace("{{ contactUrl }}", TG).replace("{{ contact }}", TG)

    # <br> внутри h1 не даёт пробела при копировании и в выдаче
    tpl = tpl.replace("Прикладная<br>эмпатия", "Прикладная <br>эмпатия", 1)

    # надзаголовок первого экрана: имя не должно разрываться по строкам
    tpl = tpl.replace("от\u00a0Виолы Маро", "от\u00a0Виолы\u00a0Маро")

    # ── сноска про Meta у самого упоминания (требование правового ТЗ) ──────
    if tpl.count("Инстаграме") != 1:
        raise ValueError("ожидалось одно упоминание Инстаграма, найдено %d" % tpl.count("Инстаграме"))
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


def font_css():
    out = []
    for fam, fname, weight, urange in FONT_FACES:
        out.append(
            "@font-face{font-family:'%s';font-style:normal;font-weight:%s;font-display:swap;"
            "src:url(/assets/fonts/%s) format('woff2');unicode-range:%s}"
            % (fam, weight, fname, urange))
    return "\n".join(out)


def copy_fonts():
    dst = os.path.join(OUT, "assets", "fonts")
    os.makedirs(dst, exist_ok=True)
    total = 0
    for _fam, fname, _w, _u in FONT_FACES:
        s = os.path.join(BUILD_ASSETS, "fonts", fname)
        shutil.copy2(s, os.path.join(dst, fname))
        total += os.path.getsize(s)
    print("  шрифты: %d файлов, %.0f КБ" % (len(FONT_FACES), total / 1024))


# ──────────────────────────────────────────────────────────────────── CSS ──

def build_css():
    css = font_css() + "\n\n" + read(os.path.join(BUILD_ASSETS, "base.css"))
    css += "\n\n/* состояния наведения и фокуса, перенесённые из инлайновых стилей */\n"
    css += hover_css() + "\n"
    write(os.path.join(OUT, "assets", "site.css"), css)
    print("  site.css: %.0f КБ" % (len(css.encode()) / 1024))


def build_js():
    js = read(os.path.join(BUILD_ASSETS, "site.js")) + "\n" + COOKIE_JS
    write(os.path.join(OUT, "assets", "site.js"), js)


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#2B211C"/>
  <text x="32" y="45" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif"
        font-size="38" fill="#E4C08A">Э</text>
</svg>
"""


def build_favicon():
    write(os.path.join(OUT, "assets", "favicon.svg"), FAVICON)


# ─────────────────────────────────────────────────────────────────── main ──

def parse_args(argv):
    global BASE, NOINDEX
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--base":
            i += 1
            BASE = "/" + argv[i].strip("/")
        elif a.startswith("--base="):
            BASE = "/" + a.split("=", 1)[1].strip("/")
        elif a == "--noindex":
            NOINDEX = True
        else:
            sys.exit("неизвестный аргумент: %s" % a)
        i += 1


def main():
    parse_args(sys.argv[1:])
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    print("Сборка сайта → site/")
    if BASE:
        print("  подпуть: %s" % BASE)
    if NOINDEX:
        print("  индексация запрещена")
    copy_fonts()
    build_images()
    build_landing()          # заполняет HOVER_RULES
    build_docs()
    build_css()              # поэтому идёт после
    build_js()
    build_favicon()

    total = 0
    for dirpath, _dirs, files in os.walk(OUT):
        for f in files:
            total += os.path.getsize(os.path.join(dirpath, f))
    print("Готово. Всего %.0f КБ" % (total / 1024))


if __name__ == "__main__":
    main()
