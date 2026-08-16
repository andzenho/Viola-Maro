/**
 * Приём заявок с лендинга «Прикладная эмпатия» в Google Таблицу.
 *
 * Устанавливается в саму таблицу: Расширения → Apps Script → вставить этот
 * файл → Развернуть → Веб-приложение. Пошагово — в README.md рядом.
 *
 * Запрос приходит с Content-Type: text/plain, а не application/json.
 * Это не небрежность: text/plain делает запрос «простым» по правилам CORS,
 * и браузер не шлёт предварительный OPTIONS. Apps Script на OPTIONS отвечать
 * не умеет, поэтому с application/json заявка не дошла бы вовсе.
 */

// ─────────────────────────────────────────────────────────────── настройка ──

/** Лист, в который падают заявки. Создастся сам, если его нет. */
const SHEET_NAME = 'Лиды';

/** Общая строка с сайтом. Должна совпадать с FORM_SECRET в site.js.
 *  Замените на свою — любая длинная случайная строка.
 *  Это не защита данных: строка лежит в коде страницы и видна любому, кто
 *  откроет исходник. Это фильтр от ботов, которые находят адрес формы
 *  переборам и шлют мусор. */
const SECRET = 'ЗАМЕНИТЕ-НА-СВОЮ-СЛУЧАЙНУЮ-СТРОКУ';

/** Кому писать о новой заявке. Пустая строка — не уведомлять. */
const NOTIFY_EMAIL = '';

// ──────────────────────────────────────────────────────────────── колонки ──

const FIELDS = [
  ['received_at',          'Получено'],
  ['plan',                 'Тариф'],
  ['name',                 'Имя'],
  ['phone',                'Телефон'],
  ['telegram',             'Telegram'],
  ['accept_offer',         'Оферта'],
  ['accept_pd',            'Согласие на ПД'],
  ['accept_ads',           'Реклама'],
  ['consent_ts',           'Время акцепта'],
  ['doc_version_offer',    'Ред. оферты'],
  ['doc_version_annex',    'Ред. приложения'],
  ['doc_version_consent',  'Ред. согласия'],
  ['page',                 'Страница'],
  ['ua',                   'User-Agent'],
];

// ─────────────────────────────────────────────────────────────── обработка ──

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    // без блокировки две одновременные заявки могут лечь в одну строку
    lock.waitLock(20000);

    let data;
    try {
      data = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    } catch (err) {
      return reply(400, { ok: false, error: 'bad json' });
    }

    if (SECRET && data.secret !== SECRET) {
      return reply(403, { ok: false, error: 'forbidden' });
    }

    // приманка для ботов: поле скрыто от человека, заполнить его может только робот
    if (data.website) {
      return reply(200, { ok: true });   // тихо принимаем и никуда не пишем
    }

    if (!String(data.name || '').trim()) {
      return reply(400, { ok: false, error: 'no name' });
    }
    if (!String(data.phone || '').trim() && !String(data.telegram || '').trim()) {
      return reply(400, { ok: false, error: 'no contact' });
    }
    if (data.accept_offer !== true || data.accept_pd !== true) {
      return reply(400, { ok: false, error: 'no consent' });
    }

    data.received_at = new Date();

    const sheet = getSheet();
    sheet.appendRow(FIELDS.map(function (f) {
      const v = data[f[0]];
      if (v === true) return 'да';
      if (v === false) return 'нет';
      return v === undefined || v === null ? '' : v;
    }));

    notify(data);
    return reply(200, { ok: true });

  } catch (err) {
    console.error(err);
    return reply(500, { ok: false, error: 'server' });
  } finally {
    try { lock.releaseLock(); } catch (err) {}
  }
}

/** Открытие адреса в браузере — чтобы видеть, что развёртывание живо. */
function doGet() {
  return reply(200, { ok: true, service: 'lead-intake' });
}

// ──────────────────────────────────────────────────────────── вспомогательное ──

function getSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(SHEET_NAME);

  if (sheet.getLastRow() === 0) {
    const header = FIELDS.map(function (f) { return f[1]; });
    sheet.appendRow(header);
    sheet.getRange(1, 1, 1, header.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function notify(data) {
  if (!NOTIFY_EMAIL) return;
  try {
    MailApp.sendEmail({
      to: NOTIFY_EMAIL,
      subject: 'Заявка с сайта: ' + (data.plan || 'без тарифа'),
      body: [
        'Имя: ' + (data.name || ''),
        'Телефон: ' + (data.phone || '—'),
        'Telegram: ' + (data.telegram || '—'),
        'Тариф: ' + (data.plan || '—'),
        'Реклама: ' + (data.accept_ads ? 'согласен' : 'нет'),
        '',
        SpreadsheetApp.getActiveSpreadsheet().getUrl(),
      ].join('\n'),
    });
  } catch (err) {
    console.error('notify failed', err);   // письмо не должно ронять приём заявки
  }
}

/**
 * Apps Script не даёт задать код ответа: наружу всегда уходит 200.
 * Поэтому результат лежит в теле, в поле ok, и сайт проверяет именно его,
 * а не res.ok. Первый аргумент оставлен для читаемости кода выше.
 */
function reply(_status, obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
