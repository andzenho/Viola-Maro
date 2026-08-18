/* Прикладная эмпатия — поведение страницы.
   Ноль зависимостей, ноль внешних запросов. */

(function () {
  'use strict';

  /* ─────────────────────────────────────────────────── настройка ──
     Заполняется один раз перед публикацией.

     LEAD_ENDPOINT — адрес веб-приложения Apps Script при таблице, куда
       падают и результаты теста эмпата. Заявка с предзаписи ложится
       в лист «Предзапись с сайта», с оплаты — в «Заявки на продукт».
       Код скрипта — в integrations/google-sheets/.
       Пока пусто, форма не делает вид, что заявка принята: она
       проверяет согласия и отправляет человека в службу заботы.

     FORM_SECRET — та же строка, что SECRET в Code.gs. Отсекает ботов.

     PAY_URLS — страницы оплаты GetPlatinum, по одной на тариф. И прямая
       оплата, и рассрочка ведут на ту же страницу: способ человек выбирает
       уже там. Переход происходит после того, как согласия записаны. */

  var LEAD_ENDPOINT = 'https://script.google.com/macros/s/AKfycbxjnSIU9If91sGwI7yr1bFQhHJq77VWDtI9eUY4eF2L4CQ06hkNLKs4kQWi-vuX6qFa_w/exec';
  var FORM_SECRET = 'PxlGXL9bQSjc0dHcLoiCZJZWtNdfv9D8yY9SHBuJ';

  var PAY_URLS = {
    basic: 'https://anny-nizh.getplatinum.ru/payment/JQqAJkS',
    full:  'https://anny-nizh.getplatinum.ru/payment/ppgQJJ7',
    bron:  ''            // страница оплаты брони 5 000 ₽ — ждёт адреса
  };

  var SUPPORT_TG = 'https://t.me/violamarohelper';

  /* Закрытый канал Виолы — куда уходит человек после заявки на предзапись. */
  var CHANNEL_URL = 'https://t.me/+iIqJoSn2UBU3Yzky';

  /* Редакции документов на момент акцепта — уходят вместе с заявкой
     и должны меняться вместе с текстом документов. */
  var DOC_VERSIONS = {
    doc_version_offer: '2026-08-10',
    doc_version_annex: '2026-08-10',
    doc_version_consent: '2026-08-10'
  };

  /* ───────────────────────────────────────────────────── модалка ── */

  var modal = document.getElementById('lead-modal');
  if (!modal) return;

  /* Чем кончается отправка: 'pay' — страница оплаты, 'channel' — закрытый
     канал. Задаётся в разметке, чтобы скрипт остался один на обе версии. */
  var AFTER = modal.getAttribute('data-after') || 'pay';
  var IS_PRE = AFTER === 'channel';

  var planLabel = document.getElementById('form-plan');
  var errBox = document.getElementById('form-error');
  var errText = document.getElementById('form-error-text');
  var sentBox = document.getElementById('form-sent');
  var submit = document.getElementById('form-submit');
  var closers = modal.querySelectorAll('[data-close-form]');

  var inputs = {
    name: modal.querySelector('[name="name"]'),
    phone: modal.querySelector('[name="phone"]'),
    tg: modal.querySelector('[name="tg"]')
  };

  var boxes = {
    accept_offer: modal.querySelector('[name="accept_offer"]'),
    accept_pd: modal.querySelector('[name="accept_pd"]'),
    accept_ads: modal.querySelector('[name="accept_ads"]')
  };

  var CB_MESSAGES = {
    accept_offer: 'Без принятия оферты оплата невозможна',
    accept_pd: IS_PRE ? 'Без согласия на обработку данных заявку оформить нельзя'
                      : 'Без согласия на обработку данных оплата невозможна'
  };

  var lastTrigger = null;
  var currentPlan = '';
  var currentPay = '';

  function errorFor(box) {
    var row = box.closest('label');
    return row ? row.querySelector('.cb-err') : null;
  }

  /* На предзаписи галки про оферту нет вовсе, поэтому проверяем только те,
     что реально есть на странице. */
  var required = ['accept_offer', 'accept_pd'].filter(function (k) { return boxes[k]; });

  function requiredOk() {
    return required.every(function (k) { return boxes[k].checked; });
  }

  function syncSubmit() {
    submit.disabled = !requiredOk();
  }

  function showCheckboxErrors(mark) {
    required.forEach(function (key) {
      var slot = errorFor(boxes[key]);
      if (!slot) return;
      var bad = mark && !boxes[key].checked;
      slot.textContent = bad ? CB_MESSAGES[key] : '';
      slot.hidden = !bad;
    });
  }

  Object.keys(boxes).forEach(function (key) {
    var box = boxes[key];
    if (!box) return;
    box.addEventListener('change', function () {
      showCheckboxErrors(true);
      syncSubmit();
      hide(errBox);
    });
  });

  function hide(el) { if (el) el.hidden = true; }

  function show(el) { if (el) el.hidden = false; }

  function fail(message) {
    if (errText) errText.textContent = message;
    show(errBox);
    hide(sentBox);
  }

  function openModal(plan, payKey, trigger) {
    currentPlan = plan;
    currentPay = payKey || '';
    lastTrigger = trigger || null;
    if (planLabel) planLabel.textContent = plan;
    hide(errBox);
    hide(sentBox);
    showCheckboxErrors(false);
    syncSubmit();
    modal.hidden = false;
    document.body.classList.add('modal-open');
    var first = closers[0] || inputs.name;
    if (first) first.focus();
  }

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove('modal-open');
    if (lastTrigger) lastTrigger.focus();
  }

  Array.prototype.forEach.call(closers, function (btn) {
    btn.addEventListener('click', closeModal);
  });

  modal.addEventListener('click', function (e) {
    if (e.target === modal.firstElementChild) closeModal();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !modal.hidden) closeModal();
  });

  /* удержание фокуса внутри открытой модалки */
  modal.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab') return;
    var focusable = modal.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  /* ─────────────────────────────────── кнопки тарифов и рассрочки ── */

  Array.prototype.forEach.call(document.querySelectorAll('[data-open-form]'), function (btn) {
    btn.addEventListener('click', function (e) {
      /* Часть кнопок — ссылки с якорем: он запасной путь, если скрипта нет. */
      if (btn.tagName === 'A') e.preventDefault();
      openModal(btn.getAttribute('data-open-form'),
                btn.getAttribute('data-pay'), btn);
    });
  });

  /* ──────────────────────────────────────────────────── отправка ── */

  submit.addEventListener('click', function () {
    var name = (inputs.name.value || '').trim();
    var phone = (inputs.phone.value || '').trim();
    var tg = (inputs.tg.value || '').trim();

    if (!name) { fail('Укажите имя.'); inputs.name.focus(); return; }
    if (!phone && !tg) { fail('Оставьте телефон или Telegram для связи.'); inputs.phone.focus(); return; }

    if (!requiredOk()) {
      showCheckboxErrors(true);
      fail(required.length > 1 ? 'Отметьте оба обязательных согласия.'
                               : 'Отметьте обязательное согласие.');
      var missing = required.filter(function (k) { return !boxes[k].checked; })[0];
      boxes[missing].focus();
      return;
    }

    var honey = modal.querySelector('[name="website"]');

    var payload = {
      secret: FORM_SECRET,
      website: honey ? honey.value : '',   // приманка: человек её не видит
      name: name,
      phone: phone,
      telegram: tg,
      plan: currentPlan,
      form: IS_PRE ? 'предзапись' : 'оплата',
      readiness: (modal.querySelector('[name="readiness"]:checked') || {}).value || '',
      accept_offer: !!(boxes.accept_offer && boxes.accept_offer.checked),
      accept_pd: !!(boxes.accept_pd && boxes.accept_pd.checked),
      accept_ads: !!(boxes.accept_ads && boxes.accept_ads.checked),
      consent_ts: new Date().toISOString(),
      page: window.location.href,
      ua: navigator.userAgent
    };
    Object.keys(DOC_VERSIONS).forEach(function (k) { payload[k] = DOC_VERSIONS[k]; });

    /* Переход на оплату. Согласия пишутся до платежа — так требует
       раздел 3 правового ТЗ: акцепт оферты должен быть зафиксирован
       раньше, чем человек расстался с деньгами. */
    function goToPayment() {
      if (IS_PRE) {
        hide(errBox);
        show(sentBox);
        window.location.href = CHANNEL_URL;
        return;
      }
      var url = PAY_URLS[currentPay];
      if (!url) {
        fail('Не нашли страницу оплаты для этого тарифа. Напишите нам в Telegram: ' + SUPPORT_TG);
        syncSubmit();
        return;
      }
      hide(errBox);
      show(sentBox);
      window.location.href = url;
    }

    if (!LEAD_ENDPOINT) {
      /* Запись согласий не подключена. Продажу не блокируем, но и молча
         терять акцепт нельзя — поэтому уходим на оплату, оставив след
         в консоли. Заполните LEAD_ENDPOINT, и эта ветка исчезнет. */
      console.warn('LEAD_ENDPOINT не задан: согласие не записано');
      goToPayment();
      return;
    }

    submit.disabled = true;
    hide(errBox);

    /* text/plain, а не application/json: так запрос считается «простым»
       и браузер не шлёт предварительный OPTIONS, на который Apps Script
       отвечать не умеет. Тело при этом остаётся JSON. */
    fetch(LEAD_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.json();
    }).then(function (body) {
      /* Apps Script всегда отвечает 200, результат лежит в теле. */
      if (!body || body.ok !== true) throw new Error(body && body.error);
      goToPayment();
    }).catch(function () {
      /* Записать не вышло. Продажу не блокируем: даём уйти на оплату
         вручную, но об этом говорим прямо, а не делаем вид, что всё цело. */
      syncSubmit();
      var url = IS_PRE ? CHANNEL_URL : (PAY_URLS[currentPay] || SUPPORT_TG);
      if (errText) {
        errText.textContent = 'Не удалось сохранить ваши данные. ';
        var a = document.createElement('a');
        a.href = url;
        a.textContent = IS_PRE ? 'Открыть закрытый канал' : 'Перейти к оплате';
        a.style.color = 'inherit';
        errText.appendChild(a);
        errText.appendChild(document.createTextNode(
          ' — или напишите нам в Telegram: ' + SUPPORT_TG));
      }
      show(errBox);
      hide(sentBox);
    });
  });

  syncSubmit();
})();

/* ─────────────────────── первый экран: высота не пляшет при скролле ──
   Высота задана в долях экрана, а на телефоне экран «дышит»: при скролле
   прячется адресная строка, высота растёт, кадр внутри пересчитывается —
   и портрет заметно наезжает. Единица svh это чинит, но её не знают
   старые iOS и встроенные браузеры мессенджеров, а именно оттуда чаще
   всего и открывают ссылку.

   Поэтому высота считается один раз при загрузке и прибивается в пикселях.
   Пересчёт — только когда меняется ШИРИНА, то есть при повороте экрана:
   изменение одной высоты и есть та самая уехавшая адресная строка. */

(function () {
  'use strict';

  var stage = document.querySelector('[data-hero-stage]');
  if (!stage || !window.matchMedia) return;

  var phone = window.matchMedia('(max-width: 760px)');
  var pinnedWidth = null;

  function pin() {
    if (!phone.matches) {
      stage.style.removeProperty('min-height');
      pinnedWidth = null;
      return;
    }
    /* Прибивается минимум, а не высота: если текста больше, экран должен
       вырасти под него, иначе кнопка уедет за обрезанный край. */
    var h = Math.min(Math.max(window.innerHeight * 0.94, 600), 960);
    stage.style.setProperty('min-height', Math.round(h) + 'px', 'important');
    pinnedWidth = window.innerWidth;
  }

  pin();

  window.addEventListener('resize', function () {
    if (window.innerWidth !== pinnedWidth) pin();
  });

  window.addEventListener('orientationchange', function () {
    setTimeout(pin, 250);            // размеры устаканиваются не сразу
  });

  if (phone.addEventListener) phone.addEventListener('change', pin);
})();

/* ───────────────────────────────────────── срок предзаписи ──
   Таймер противоречит красной линии проекта: обратные отсчёты в брифе
   запрещены прямой правкой эксперта. Поставлен по решению заказчика,
   поэтому сделан максимально тихо — палитра страницы, без красного,
   без мигания и без «осталось N мест».

   Когда срок вышел, полоса не показывает нули и не остаётся висеть:
   она убирается целиком. Нули читаются как сломанная страница. */

(function () {
  'use strict';

  var box = document.getElementById('countdown');
  if (!box) return;

  var band = document.getElementById('srok');
  var target = Date.parse(box.getAttribute('data-deadline'));
  if (isNaN(target)) { if (band) band.hidden = true; return; }

  var cells = {
    d: box.querySelector('[data-cd="d"]'),
    h: box.querySelector('[data-cd="h"]'),
    m: box.querySelector('[data-cd="m"]'),
    s: box.querySelector('[data-cd="s"]')
  };

  function two(n) { return n < 10 ? '0' + n : String(n); }

  function tick() {
    var left = target - Date.now();
    if (left <= 0) {
      if (band) band.hidden = true;
      clearInterval(timer);
      return;
    }
    var sec = Math.floor(left / 1000);
    cells.d.textContent = String(Math.floor(sec / 86400));
    cells.h.textContent = two(Math.floor(sec / 3600) % 24);
    cells.m.textContent = two(Math.floor(sec / 60) % 60);
    cells.s.textContent = two(sec % 60);
  }

  tick();
  var timer = setInterval(tick, 1000);
})();
