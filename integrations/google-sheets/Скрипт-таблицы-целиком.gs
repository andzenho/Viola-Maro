/**
 * Приёмник таблицы: тест «Есть у вас способности эмпата?» и заявки с сайтов.
 *
 * Сервер не нужен: это скрипт внутри самой таблицы, Google сам держит адрес,
 * по которому страницы присылают данные.
 *
 * Листы:
 *   «Тест эмпата»        — сырьё теста
 *   «Предзапись с теста» — заявки из приложения теста
 *   «Предзапись с сайта» — заявки с сайта предзаписи
 *   «Заявки на продукт»  — заявки с сайта оплаты и брони
 *
 * После правок: Развернуть → Управление развёртываниями → карандаш →
 * новая версия. Адрес при этом не меняется.
 */

/* ═══ ИМЕНА ВКЛАДОК — ЕДИНСТВЕННОЕ МЕСТО, ГДЕ ОНИ ЗАДАЮТСЯ ═══════════
   Раньше эти имена лежали в четырёх разных местах файла, и одно из них
   при переименовании пропустили — 18 августа живые заявки два часа падали
   в лист-двойник. Теперь место одно, и сравнение больше не дословное:
   лишний пробел, другой регистр и «е» вместо «ё» вкладку не потеряют
   (см. найтиЛист_). Новая вкладка создаётся только если похожей нет вообще.

   Проверить, что всё сходится: выбрать в списке функций «проверитьЛисты»
   и нажать «Выполнить». Скажет, какая вкладка какой строке соответствует. */
var ЛИСТЫ = {
  тест:        'Тест эмпата',           // сырьё теста
  предзапись:  'Предзапись с теста',    // заявки из приложения теста
  сайтПред:    'Предзапись с сайта',    // заявки с сайта предзаписи
  сайтОплата:  'Заявки на продукт'      // заявки с сайта оплаты и брони
};
/* ════════════════════════════════════════════════════════════════════ */

/* Штамп развёрнутой версии. Открыть адрес /exec в браузере — он покажет,
   какая версия скрипта РАБОТАЕТ. Веб-приложение выполняет не то, что открыто
   в редакторе, а то, что развёрнуто: сохранить — не значит развернуть.
   Если в ответе не эта дата, развёртывание старое. */
var ВЕРСИЯ = '2026-08-18 №3';

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

var SITE_SHEETS = {
  'предзапись': ЛИСТЫ.сайтПред,
  'оплата': ЛИСТЫ.сайтОплата
};

/** Общая строка с сайтом. Совпадает с FORM_SECRET в site.js. */
var SITE_SECRET = 'PxlGXL9bQSjc0dHcLoiCZJZWtNdfv9D8yY9SHBuJ';

var SITE_FIELDS = [
  ['received_at',         'Дата'],
  ['name',                'Имя'],
  ['phone',               'Телефон'],
  ['telegram',            'Телеграм'],
  ['readiness',           'Готовность'],     // только у предзаписи
  ['plan',                'Тариф'],          // только у оплаты
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
    var raw = e && e.parameter && e.parameter.payload;
    if (!raw) return json_({ ok: true, note: 'Приёмник заявок жив', версия: ВЕРСИЯ });
    return route_(JSON.parse(raw));
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function route_(d) {
  try {
    if (d.form === 'предзапись' || d.form === 'оплата') { return saveSite_(d); }
    if (d.type === 'lead') { return saveLead_(d); }

    var sheet = getSheet_();
    var s = d.scales || {};

    sheet.appendRow([
      new Date(),
      d.userId || '',
      d.userName || '',
      rankName_(d.rank),
      d.percent || '',
      s.A, s.P, s.I, s.B, s.C, s.G, s.L, s.F, s.K,
      pick_(d.forks, 'bol'), pick_(d.forks, 'zapros'),
      pick_(d.forks, 'opyt'), pick_(d.forks, 'davno'),
      (d.answers || []).join(','),
      d.seconds || '', d.fast ? 'да' : '', d.monotone ? 'да' : ''
    ]);

    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/** Заявка на предзапись — отдельным листом, чтобы не мешать сырьё теста и контакты. */
function saveLead_(d) {
  var sheet = getSheet2_(LEAD_SHEET, LEAD_HEADERS);
  sheet.appendRow([
    new Date(),
    d.name || '',
    d.contact || '',
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
  return json_({ ok: true });
}

/** Заявка с сайта предзаписи или с сайта оплаты. */
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
  // Оферту принимают только при оплате: на предзаписи покупки нет,
  // значит нет и акцепта. Согласие на обработку данных нужно всегда.
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

  return json_({ ok: true });
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

/**
 * Ищет вкладку по имени, прощая мелкие расхождения.
 *
 * getSheetByName сравнивает дословно. Лишний пробел в конце, другой регистр,
 * «е» вместо «ё» — и вкладка «не найдена», а скрипт заводит рядом двойник
 * и пишет в него. Именно так 18 августа разъехались «Предзапись»
 * и «Предзапись с теста».
 *
 * Поэтому сначала точное совпадение, потом — по упрощённому виду имени.
 * Возвращает null, если похожей вкладки нет: создавать её — дело вызывающего.
 */
function найтиЛист_(имя) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var точно = ss.getSheetByName(имя);
  if (точно) return точно;

  var цель = упростить_(имя);
  var листы = ss.getSheets();
  for (var i = 0; i < листы.length; i++) {
    if (упростить_(листы[i].getName()) === цель) return листы[i];
  }
  return null;
}

/** Имя без регистра, без краевых и двойных пробелов, «ё» = «е». */
function упростить_(имя) {
  return String(имя)
    .replace(/\u00a0/g, ' ')   // неразрывный пробел приезжает из копипаста
    .replace(/\s+/g, ' ')
    .replace(/ё/g, 'е')
    .trim()
    .toLowerCase();
}

function getSheet2_(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = найтиЛист_(name) || ss.insertSheet(name);

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
    sheet.setFrozenRows(1);
    return sheet;
  }

  /* Лист уже с данными, а состав колонок поменялся — переписываем шапку.
     Без этого новые поля легли бы в столбцы без названий, а старые остались
     бы подписаны по-прежнему. Строки с данными не трогаем. */
  if (sheet.getMaxColumns() < headers.length) {
    sheet.insertColumnsAfter(sheet.getMaxColumns(), headers.length - sheet.getMaxColumns());
  }
  var have = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  var same = true;
  for (var i = 0; i < headers.length; i++) {
    if (String(have[i]) !== headers[i]) { same = false; break; }
  }
  if (!same) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = найтиЛист_(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
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

/* ───────────────────────────── уборка тестовых строк ──
   Запускается вручную из редактора: выбрать в списке функций
   «удалитьТестовыеСтроки» и нажать «Выполнить».

   Удаляет только те строки, где имя начинается с «ТЕСТ». Настоящие заявки
   не трогает: под удаление попадает ровно то, что мы сами и пометили.
   Колонка «Имя» ищется по заголовку, а не по номеру, — у листов разный
   порядок столбцов, и жёсткий индекс однажды снёс бы не то. */

function удалитьТестовыеСтроки() {
  var листы = [ЛИСТЫ.тест, ЛИСТЫ.предзапись, ЛИСТЫ.сайтПред, ЛИСТЫ.сайтОплата];
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var отчёт = [];

  листы.forEach(function (имя) {
    var sheet = найтиЛист_(имя);
    if (!sheet || sheet.getLastRow() < 2) return;

    var данные = sheet.getDataRange().getValues();
    var колонка = данные[0].indexOf('Имя');
    if (колонка === -1) return;

    /* Идём снизу вверх: при удалении сверху номера оставшихся строк
       съезжают, и половина попала бы мимо. */
    var удалено = 0;
    for (var i = данные.length - 1; i >= 1; i--) {
      var значение = String(данные[i][колонка] || '').trim();
      if (значение.toUpperCase().indexOf('ТЕСТ') === 0) {
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
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var есть = ss.getSheets().map(function (s) { return s.getName(); });
  var строки = [];

  Object.keys(ЛИСТЫ).forEach(function (ключ) {
    var имя = ЛИСТЫ[ключ];
    var sheet = найтиЛист_(имя);
    if (!sheet) {
      строки.push('✘ ' + ключ + ': «' + имя + '» — ВКЛАДКИ НЕТ, будет создана заново');
      return;
    }
    /* Совпало не дословно — предупреждаем: писать будем сюда, но имя стоит
       выровнять, чтобы в глазах не двоилось. */
    var приписка = sheet.getName() === имя
      ? '' : ' (в таблице она названа «' + sheet.getName() + '»)';
    строки.push('✔ ' + ключ + ': «' + имя + '»' + приписка
                + ' — строк: ' + Math.max(0, sheet.getLastRow() - 1));
  });

  var текст = 'Версия скрипта в редакторе: ' + ВЕРСИЯ + '\n\n'
    + строки.join('\n')
    + '\n\nВкладки в таблице: ' + есть.join(' | ');
  Logger.log(текст);
  try { SpreadsheetApp.getUi().alert(текст); } catch (e) {}
  return текст;
}
