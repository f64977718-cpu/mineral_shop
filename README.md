# Кам'яна Грань — магазин мінералів (Django)

## Запуск
```
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Mac/Linux: cp .env.example .env   (потім заповніть .env)
python manage.py migrate
python manage.py seed_store
python manage.py createsuperuser # створіть СВОГО адміна (логін/пароль)
python manage.py runserver
```
Сайт: http://127.0.0.1:8000/ — Адмінка: http://127.0.0.1:8000/admin/

> Готового адміна в проєкті немає: його створює `createsuperuser`.

## Адмінка і журнал візитів
`/admin/` → логін і пароль. Кожен вхід, вихід, невдала спроба входу та перегляд сторінок адмінки
записуються в таблицю **«Візити адмінів»** (час, користувач, IP, адреса, браузер).
Журнал доступний лише для читання — змінити чи видалити запис неможливо.
У адмінці також: товари (фото, галерея), замовлення, платежі, журнал подій платежів.

## Фото товарів
Адмінка → Мінерали → товар → «Головне фото» (завантажити файл) або «Або посилання на фото»,
плюс «Фото мінералу» внизу сторінки — додаткова галерея. Без фото показується намальований SVG-кристал.
Файли зберігаються в `media/`. Для продакшну тримайте їх у S3-сумісному сховищі/CDN (django-storages).

## Оплата (як гроші не губляться)
1. Картку клієнт вводить **на сторінці провайдера** (Stripe / LiqPay) — на наш сервер дані картки не потрапляють.
2. Суму рахує сервер за цінами з БД; товар резервується на складі в транзакції.
3. «Оплачено» ставиться тільки після **підписаного вебхука** (`/webhooks/stripe/`, `/webhooks/liqpay/`), а не за поверненням браузера.
4. Кожна подія пишеться в `PaymentEvent` з унікальним (provider, event_id) — повтор вебхука нічого не дублює.
5. Сума й валюта в події звіряються з очікуваними; розбіжність → прапорець «потрібна перевірка», замовлення не оплачується.
6. Страховка від втрачених вебхуків — команди (запускайте за cron кожні 5 хв):
   ```
   python manage.py reconcile_payments && python manage.py expire_orders
   ```
   `reconcile_payments` питає провайдера про «завислі» платежі; `expire_orders` скасовує неоплачені замовлення й повертає товар на склад.
   Якщо гроші прийшли вже після скасування — замовлення відновлюється або помічається для ручного повернення.

### Підключення Stripe
`.env`: `PAYMENT_PROVIDER=stripe`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SITE_URL`.
У Stripe Dashboard → Webhooks додайте `https://ВАШ-САЙТ/webhooks/stripe/` з подіями:
`checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`.
Локально: `stripe listen --forward-to localhost:8000/webhooks/stripe/`.
Увага: Stripe відкриває акаунти лише для компаній у підтримуваних країнах (України серед них немає), перевірте також, чи підтримується ваша валюта.

### Підключення LiqPay
`.env`: `PAYMENT_PROVIDER=liqpay`, `LIQPAY_PUBLIC_KEY`, `LIQPAY_PRIVATE_KEY`, `SITE_URL` (публічний https-адрес — LiqPay має достукатись до `/webhooks/liqpay/`).
Для тестів: `LIQPAY_SANDBOX=1`.

### Розробка без ключів
`PAYMENT_PROVIDER=mock` (лише при `DJANGO_DEBUG=1`) — сторінка-імітація провайдера, що проходить через ту саму ідемпотентну логіку.

## База Aiven
У `.env` заповніть `DB_HOST`, `DB_PASSWORD` (порт 28433, `DB_NAME=defaultdb`, сертифікат `certs/aiven-ca.pem` уже налаштовані), потім `python manage.py migrate`.
Якщо `DB_HOST` порожній — використовується SQLite.

## Тести
`python manage.py test store` — 27 тестів: ідемпотентність, підписи Stripe/LiqPay, підміна суми, пізня оплата, журнал адмінів тощо.

## Продакшн-чекліст
`DJANGO_DEBUG=0`, власний `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, HTTPS, зміна пароля БД, сильні паролі адмінів
(бажано змінити адресу `/admin/` та додати 2FA / django-axes проти підбору паролів), резервні копії БД, `collectstatic`.
