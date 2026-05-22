# WB Marketing Notifications

Подпроект для логики "ВБ маркетинг уведомления".

Этот подпроект выделен отдельно от `wb-fbo-supply-notifications`, чтобы новые маркетинговые уведомления не ломали действующий FBO-отчет.

## Planned Scope

Здесь будет жить отдельная логика:

- сбор маркетинговых данных WB;
- правила попадания товаров/кампаний в уведомление;
- формат текстового сообщения;
- формат Markdown-файла, если он нужен;
- отправка в отдельный чат Пачки;
- отдельный GitHub Actions workflow;
- отдельный Cloudflare Worker для расписания.

## Next Inputs Needed

Перед реализацией нужно определить:

- id чата Пачки;
- расписание;
- источники данных;
- условия попадания в уведомление;
- формат сообщения;
- нужен ли Markdown-файл;
- нужен ли тред и кого тегать.

Подробный рабочий контекст будет в `PROJECT_CONTEXT.md`.

## Pachca Chats

- Test chat: `39363429`.
- Production chat: `36815841`.

New notification logic should be tested in the test chat first, then switched to production after confirmation.
