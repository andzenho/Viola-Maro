/**
 * Приёмник таблицы: тест «Есть у вас способности эмпата?» и заявки с сайтов.
 *
 * Сервер не нужен: это скрипт внутри самой таблицы, Google сам держит адрес,
 * по которому страницы присылают данные.
 *
 * Листы:
 *   «Тест эмпата»        — сырьё теста
 *   «Предзапись»         — заявки из приложения теста
 *   «Предзапись с сайта» — заявки с сайта предзаписи
 *   «Заявки на продукт»  — заявки с сайта оплаты
 *
 * После правок: Развернуть → Управление развёртываниями → карандаш →
 * новая версия. Адрес при этом не меняется.
 */

var SHEET_NAME = 'Тест эмпата';
var LEAD_SHEET = 'Предзапись';

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

/* ── заявки с сайтов ───────────────────────────────────────────────────
   Имена ровно как у вкладок в таблице. Если разойдутся хоть на символ,
   скрипт молча заведёт рядом новую вкладку с таким именем, а вы будете
   ждать заявки в старой. */
var SITE_SHEETS = {
  'предзапись': 'Предзапись с сайта',
  'оплата': 'Заявки на продукт'
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
    if (!raw) return json_({ ok: true, note: 'Приёмник теста эмпата жив' });
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
    return (v === undefined || v === null) ? '' : v;
  }));

  return json_({ ok: true });
}

function getSheet2_(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name) || ss.insertSheet(name);

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
