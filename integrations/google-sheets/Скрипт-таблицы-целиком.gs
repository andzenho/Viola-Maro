/**
 * Приёмник таблицы: тест «Есть у вас способности эмпата?» и заявки с сайтов.
 *
 * Сервер не нужен: это скрипт внутри самой таблицы, Google сам держит адрес,
 * по которому страницы присылают данные.
 *
 * ⚠ После правок обязательно: Развернуть → Управление развёртываниями →
 * карандаш → Версия: «Новая версия» → Развернуть. Сохранение файла (Ctrl+S)
 * на работающий адрес НЕ влияет: он отдаёт закреплённую версию, а не редактор.
 * Проверить, что развернулось: открыть адрес /exec в браузере — в ответе
 * будет поле «версия». Не совпало с числом ниже — развёртывание старое.
 */

var ВЕРСИЯ = '2026-08-19 №2';

/* ═══ ИМЕНА ВКЛАДОК — ЕДИНСТВЕННОЕ МЕСТО, ГДЕ ОНИ ЗАДАЮТСЯ ═══════════
   Должны совпадать с именами вкладок в таблице ДОСЛОВНО. Разойдутся хоть
   на пробел — скрипт молча заведёт рядом новую вкладку и будет писать
   в неё, а вы будете ждать заявки в старой. Так уже случилось 18 августа.

   Проверить, что всё сходится: выбрать в списке функций «проверитьЛисты»
   и нажать «Выполнить». Скажет, какие вкладки не найдены. */
var ЛИСТЫ = {
  тест:        'Тест эмпата',           // сырьё теста
  предзапись:  'Предзапись с теста',    // заявки из приложения теста
  сайтПред:    'Предзапись с сайта',    // заявки с сайта предзаписи
  сайтОплата:  'Заявки на продукт'      // заявки с сайта оплаты и брони
};
/* ════════════════════════════════════════════════════════════════════ */

var SHEET_NAME = ЛИСТЫ.тест;
var LEAD_SHEET = ЛИСТЫ.предзапись;

var HEADERS = [
  'Дата', 'ID в Телеграме', 'Имя',
  'Ранг', 'Процент',
  'Дар', 'Прилипание', 'История', 'Тело', 'Адресат', 'Гигиена', 'Люди', 'Фон', 'Контроль',
  'Где съедает', 'Что менять первым', 'Что уже делали', 'Давно смотрит',
  'Ответы (1–24)',
  'Секунд', 'Быстро', 'Одна кнопка'
];

var LEAD_HEADERS = [
  'Дата', 'Имя', 'Телеграм', 'ID в Телеграме',
  'Тип', 'Процент', 'Что менять первым', 'Где съедает', 'Готовность',
  'Согласие на ПД', 'Реклама', 'Время акцепта', 'Ред. согласия'
];

/* Какая форма в какой лист. «Заявка» и «оплата» делят один лист намеренно:
   в обоих случаях человек уже выбрал тариф, и держать их в разных вкладках
   значит дважды смотреть один и тот же список. Отличает их колонка
   «Готовность»: у заявки там «Заявка с канала, без оплаты». */
var SITE_SHEETS = {
  'предзапись': ЛИСТЫ.сайтПред,
  'оплата': ЛИСТЫ.сайтОплата,
  'заявка': ЛИСТЫ.сайтОплата
};

/** Общая строка с сайтом. Совпадает с FORM_SECRET в site.js. */
var SITE_SECRET = 'PxlGXL9bQSjc0dHcLoiCZJZWtNdfv9D8yY9SHBuJ';

var SITE_FIELDS = [
  ['received_at',         'Дата'],
  ['name',                'Имя'],
  ['phone',               'Телефон'],
  ['telegram',            'Телеграм'],
  ['readiness',           'Готовность'],     // предзапись и заявка
  ['plan',                'Тариф'],          // оплата, бронь и заявка
  ['accept_offer',        'Оферта'],
  ['accept_pd',           'Согласие на ПД'],
  ['accept_ads',          'Реклама'],
  ['consent_ts',          'Время акцепта'],
  ['doc_version_offer',   'Ред. оферты'],
  ['doc_version_annex',   'Ред. приложения'],
  ['doc_version_consent', 'Ред. согласия'],
  ['page',                'Страница'],
  ['ua',                  'User-Agent']
];

function doPost(e) {
  try {
    var d = JSON.parse(e.postData.contents);
    return route_(d);
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/**
 * Страница теста присылает данные обычным GET с параметром payload.
 * Так надёжнее: POST на веб-приложение Apps Script упирается в редирект,
 * который у анонимных запросов отдаёт «Page Not Found».
 */
function doGet(e) {
  try {
    var p = (e && e.parameter) || {};

    /* Диагностика: какие вкладки скрипт реально видит и сколько в них строк.
       Нужна снаружи — по содержимому таблицы имена листов не определить,
       и 18 августа мы на этом ошиблись с диагнозом. */
    if (p.diag) {
      if (SITE_SECRET && p.diag !== SITE_SECRET) return json_({ ok: false, error: 'forbidden' });
      return json_({ ok: true, версия: ВЕРСИЯ, вкладки: обзорЛистов_() });
    }

    if (!p.payload) {
      return json_({ ok: true, note: 'Приёмник теста эмпата жив', версия: ВЕРСИЯ, лист: LEAD_SHEET });
    }
    return route_(JSON.parse(p.payload));
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function route_(d) {
  try {
    /* Список форм — в SITE_SHEETS, чтобы новая форма подключалась одной
       строкой там, а не двумя правками в разных местах. */
    if (SITE_SHEETS[d.form]) { return saveSite_(d); }
    if (d.type === 'lead') { return saveLead_(d); }

    /* Дальше — только результат теста эмпата. Если пришла форма, которой
       скрипт ещё не знает (сайт обновили, а скрипт нет), дописывать её сюда
       нельзя: в «Тест эмпата» нет колонок под имя и телефон, строка ляжет
       пустой, а сайт покажет человеку «заявка принята». Контакт исчезнет
       молча. Честная ошибка лучше: она видна и на сайте, и здесь. */
    if (d.form) return json_({ ok: false, error: 'неизвестная форма: ' + d.form });

    var sheet = getSheet_();
    var s = d.scales || {};

    sheet.appendRow([
      new Date(),
      d.userId || '',
      какТекст_(d.userName || ''),
      rankName_(d.rank),
      d.percent || '',
      s.A, s.P, s.I, s.B, s.C, s.G, s.L, s.F, s.K,
      pick_(d.forks, 'bol'), pick_(d.forks, 'zapros'),
      pick_(d.forks, 'opyt'), pick_(d.forks, 'davno'),
      (d.answers || []).join(','),
      d.seconds || '', d.fast ? 'да' : '', d.monotone ? 'да' : ''
    ]);

    return json_({ ok: true, версия: ВЕРСИЯ, лист: sheet.getName() });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/** Заявка на предзапись — отдельным листом, чтобы не мешать сырьё теста и контакты. */
function saveLead_(d) {
  var sheet = getSheet2_(LEAD_SHEET, LEAD_HEADERS);
  sheet.appendRow([
    new Date(),
    какТекст_(d.name || ''),
    /* В поле «Телеграм» люди регулярно пишут телефон, в том числе с плюсом.
       Без защиты ячейка превращается в #ERROR!, и перезвонить некому. */
    какТекст_(d.contact || ''),
    d.userId || '',
    rankName_(d.rank),
    d.percent || '',
    pick_(d.forks, 'zapros'),
    pick_(d.forks, 'bol'),
    /* d.talk — из заявок, отправленных до 17.08: там поле называлось иначе,
       а в буфере браузера такие записи могут лежать до сих пор. */
    d.ready || d.talk || '',
    d.accept_pd || '',
    d.accept_ads || '',
    d.consent_ts || '',
    d.doc_version_consent || ''
  ]);
  /* Имя листа в ответе: видно, куда легла заявка, без чтения таблицы. */
  return json_({ ok: true, версия: ВЕРСИЯ, лист: sheet.getName() });
}

/** Заявка с сайта предзаписи, оплаты, брони или страницы заявки. */
function saveSite_(d) {
  if (SITE_SECRET && d.secret !== SITE_SECRET) {
    return json_({ ok: false, error: 'forbidden' });
  }

  // приманка для ботов: поле скрыто от человека, заполнить может только робот
  if (d.website) return json_({ ok: true });

  if (!String(d.name || '').trim()) {
    return json_({ ok: false, error: 'no name' });
  }
  if (!String(d.phone || '').trim() && !String(d.telegram || '').trim()) {
    return json_({ ok: false, error: 'no contact' });
  }
  // Оферту принимают только там, где платят прямо на сайте. На предзаписи
  // и на странице заявки покупки не происходит: требовать согласие
  // с договором купли-продажи там, где ничего не покупают, юридически
  // неверно. Согласие на обработку данных нужно всегда — контакты мы
  // собираем везде.
  if (d.accept_pd !== true) return json_({ ok: false, error: 'no consent' });
  if (d.form === 'оплата' && d.accept_offer !== true) {
    return json_({ ok: false, error: 'no offer' });
  }

  var name = SITE_SHEETS[d.form];
  if (!name) return json_({ ok: false, error: 'unknown form' });

  d.received_at = new Date();

  var headers = SITE_FIELDS.map(function (f) { return f[1]; });
  var sheet = getSheet2_(name, headers);
  sheet.appendRow(SITE_FIELDS.map(function (f) {
    var v = d[f[0]];
    if (v === true) return 'да';
    if (v === false) return 'нет';
    return (v === undefined || v === null) ? '' : какТекст_(v);
  }));

  return json_({ ok: true, версия: ВЕРСИЯ, лист: sheet.getName() });
}

/**
 * Заставляет таблицу считать значение текстом.
 *
 * Телефон люди пишут как «+7 981 875 52 25». Ведущий плюс Google Таблицы
 * читают как начало формулы — и вместо номера в ячейке оказывается
 * #ERROR!. Один живой лид мы так уже потеряли: перезвонить некому.
 *
 * Апостроф впереди — штатный признак «это текст», в самой ячейке
 * он не показывается. Проверяем ещё = - @: с них тоже начинаются формулы.
 */
function какТекст_(v) {
  var s = String(v);
  return /^[=+\-@]/.test(s) ? "'" + s : v;
}

function getSheet2_(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name) || ss.insertSheet(name);

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
    sheet.setFrozenRows(1);
    return sheet;
  }

  /* Лист уже с данными, а колонок стало больше — подписываем только пустые
     ячейки шапки. Названия, поставленные руками, не трогаем: если колонку
     переименовали в таблице, это решение человека, а не сбой.
     Строки с данными не трогаем никогда. */
  if (sheet.getMaxColumns() < headers.length) {
    sheet.insertColumnsAfter(sheet.getMaxColumns(), headers.length - sheet.getMaxColumns());
  }
  var have = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  var fixed = [];
  var need = false;
  for (var i = 0; i < headers.length; i++) {
    var cur = String(have[i] == null ? '' : have[i]).trim();
    fixed.push(cur ? have[i] : headers[i]);
    if (!cur) need = true;
  }
  if (need) {
    sheet.getRange(1, 1, 1, headers.length).setValues([fixed]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function rankName_(key) {
  var names = {
    donor: 'Эмпат-донор',
    filter: 'Эмпат без фильтра',
    sleeping: 'Спящий эмпат',
    awake: 'Проснувшийся эмпат',
    reader: 'Считывающий',
    caring: 'Сочувствующий',
    other: 'Другая настройка'
  };
  return names[key] || key || '';
}

function pick_(obj, key) {
  return (obj && obj[key]) ? obj[key] : '';
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/** Сводка по вкладкам из ЛИСТЫ: что найдено, сколько строк, что есть в таблице. */
function обзорЛистов_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var из = {};
  Object.keys(ЛИСТЫ).forEach(function (ключ) {
    var sheet = ss.getSheetByName(ЛИСТЫ[ключ]);
    из[ключ] = {
      имя: ЛИСТЫ[ключ],
      есть: !!sheet,
      строк: sheet ? Math.max(0, sheet.getLastRow() - 1) : 0
    };
  });
  из['всеВкладки'] = ss.getSheets().map(function (s) { return s.getName(); });
  return из;
}

/* ───────────────────────────── уборка тестовых строк ──
   Запускается вручную из редактора: выбрать в списке функций
   «удалитьТестовыеСтроки» и нажать «Выполнить».

   Удаляет только те строки, где имя начинается с «ТЕСТ» или «ЗОНД».
   Настоящие заявки не трогает: под удаление попадает ровно то, что мы
   сами и пометили. Колонка «Имя» ищется по заголовку, а не по номеру, —
   у листов разный порядок столбцов, и жёсткий индекс однажды снёс бы не то. */

function удалитьТестовыеСтроки() {
  var листы = [ЛИСТЫ.тест, ЛИСТЫ.предзапись, ЛИСТЫ.сайтПред, ЛИСТЫ.сайтОплата];
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var отчёт = [];

  листы.forEach(function (имя) {
    var sheet = ss.getSheetByName(имя);
    if (!sheet || sheet.getLastRow() < 2) return;

    var данные = sheet.getDataRange().getValues();
    var колонка = данные[0].indexOf('Имя');
    if (колонка === -1) return;

    /* Идём снизу вверх: при удалении сверху номера оставшихся строк
       съезжают, и половина попала бы мимо. */
    var удалено = 0;
    for (var i = данные.length - 1; i >= 1; i--) {
      var значение = String(данные[i][колонка] || '').trim().toUpperCase();
      if (значение.indexOf('ТЕСТ') === 0 || значение.indexOf('ЗОНД') === 0) {
        sheet.deleteRow(i + 1);
        удалено++;
      }
    }
    if (удалено) отчёт.push(имя + ': ' + удалено);
  });

  var текст = отчёт.length ? ('Удалено — ' + отчёт.join('; ')) : 'Тестовых строк не найдено';
  Logger.log(текст);
  try { SpreadsheetApp.getUi().alert(текст); } catch (e) {}   // из редактора UI недоступен
  return текст;
}

/* ─────────────────────────── проверка имён вкладок ──
   Запускается вручную из редактора. Показывает, какие из четырёх имён
   выше действительно существуют в таблице, а какие скрипт не находит
   и создаст заново при первой же заявке. */

function проверитьЛисты() {
  var обзор = обзорЛистов_();
  var строки = [];

  Object.keys(ЛИСТЫ).forEach(function (ключ) {
    var x = обзор[ключ];
    строки.push((x.есть ? '✔ ' : '✘ ') + ключ + ': «' + x.имя + '»'
                + (x.есть ? ' — строк: ' + x.строк : ' — ВКЛАДКИ НЕТ, будет создана заново'));
  });

  var текст = 'Версия скрипта в редакторе: ' + ВЕРСИЯ + '\n\n'
    + строки.join('\n')
    + '\n\nВкладки в таблице: ' + обзор['всеВкладки'].join(' | ');
  Logger.log(текст);
  try { SpreadsheetApp.getUi().alert(текст); } catch (e) {}
  return текст;
}
