/* Прикладная эмпатия — поведение страницы.
   Ноль зависимостей, ноль внешних запросов. */

(function () {
  'use strict';

  /* ─────────────────────────────────────────────────── настройка ──
     Заполняется один раз перед публикацией.

     LEAD_ENDPOINT — адрес веб-приложения Apps Script, которое кладёт
       заявку в Google Таблицу. Код и инструкция — в
       integrations/google-sheets/. Вид: https://script.google.com/…/exec
       Пока пусто, форма не делает вид, что заявка принята: она
       проверяет согласия и отправляет человека в службу заботы.

     FORM_SECRET — та же строка, что SECRET в Code.gs. Отсекает ботов.

     PAY_URLS — страницы оплаты GetPlatinum, по одной на тариф. И прямая
       оплата, и рассрочка ведут на ту же страницу: способ человек выбирает
       уже там. Переход происходит после того, как согласия записаны. */

  var LEAD_ENDPOINT = 'https://script.google.com/macros/s/AKfycbzoZdsZ2KFXhNbpEO2C3jbXZyM9TRCgWzwFSTi4IkkaboVaffA8EHIIjaehpfJGZWI-hw/exec';
  var FORM_SECRET = 'PxlGXL9bQSjc0dHcLoiCZJZWtNdfv9D8yY9SHBuJ';

  var PAY_URLS = {
    basic: 'https://anny-nizh.getplatinum.ru/payment/JQqAJkS',
    full:  'https://anny-nizh.getplatinum.ru/payment/ppgQJJ7'
  };

  var SUPPORT_TG = 'https://t.me/violamarohelper';

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
    accept_pd: 'Без согласия на обработку данных оплата невозможна'
  };

  var lastTrigger = null;
  var currentPlan = '';
  var currentPay = '';

  function errorFor(box) {
    var row = box.closest('label');
    return row ? row.querySelector('.cb-err') : null;
  }

  function requiredOk() {
    return boxes.accept_offer.checked && boxes.accept_pd.checked;
  }

  function syncSubmit() {
    submit.disabled = !requiredOk();
  }

  function showCheckboxErrors(mark) {
    ['accept_offer', 'accept_pd'].forEach(function (key) {
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
    btn.addEventListener('click', function () {
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
      fail('Отметьте оба обязательных согласия.');
      var missing = !boxes.accept_offer.checked ? boxes.accept_offer : boxes.accept_pd;
      missing.focus();
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
      accept_offer: boxes.accept_offer.checked,
      accept_pd: boxes.accept_pd.checked,
      accept_ads: boxes.accept_ads.checked,
      consent_ts: new Date().toISOString(),
      page: window.location.href,
      ua: navigator.userAgent
    };
    Object.keys(DOC_VERSIONS).forEach(function (k) { payload[k] = DOC_VERSIONS[k]; });

    /* Переход на оплату. Согласия пишутся до платежа — так требует
       раздел 3 правового ТЗ: акцепт оферты должен быть зафиксирован
       раньше, чем человек расстался с деньгами. */
    function goToPayment() {
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
      var url = PAY_URLS[currentPay] || SUPPORT_TG;
      if (errText) {
        errText.textContent = 'Не удалось сохранить ваши данные. ';
        var a = document.createElement('a');
        a.href = url;
        a.textContent = 'Перейти к оплате';
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
