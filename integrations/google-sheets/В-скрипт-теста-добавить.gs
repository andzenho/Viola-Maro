/**
 * ДОПОЛНЕНИЕ к вашему скрипту приёмника теста «Есть у вас способности эмпата?».
 *
 * Зачем: заявки с двух сайтов должны падать в ту же таблицу, что и тест,
 * но своими вкладками — «Сайт: предзапись» и «Сайт: оплата». Тогда все
 * контакты в одном месте, а сырьё теста не мешается с продажами.
 *
 * Как поставить:
 *   1. Откройте скрипт таблицы (Расширения → Apps Script).
 *   2. Вставьте всё, что ниже, в КОНЕЦ файла. Ваш код не трогается.
 *   3. В функции route_ добавьте первой строкой:
 *
 *          if (d.form === 'предзапись' || d.form === 'оплата') return saveSite_(d);
 *
 *      Строка про тест (d.type === 'lead') остаётся как была, ниже.
 *   4. Развернуть → Управление развёртываниями → карандаш → Версия: Новая.
 *      Адрес /exec при этом не меняется.
 *
 * Дальше пришлите мне этот адрес — пропишу его на обоих сайтах, и мой
 * отдельный приёмник можно будет удалить.
 */

/* Имена ровно как у вкладок в таблице. Если разойдутся хоть на символ,
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
