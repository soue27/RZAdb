# Локальные UI-ресурсы

Файлы в этой директории и `static/fonts` получены из официальных
источников и обслуживаются приложением через существующий `/static` mount.
Не подключать CDN как резервный источник.

| Ресурс | Зафиксированная версия | Источник | Лицензия |
| --- | --- | --- | --- |
| Bootstrap CSS и Bundle | 5.3.8 | [официальный релиз](https://github.com/twbs/bootstrap/releases/tag/v5.3.8), архив `bootstrap-5.3.8-dist.zip` | MIT, `bootstrap/LICENSE` |
| HTMX | 2.0.7 | [официальный тег](https://github.com/bigskysoftware/htmx/tree/v2.0.7), `dist/htmx.min.js` | Zero-Clause BSD (0BSD), `htmx/LICENSE` |
| Roboto | API revision v51; веса 300, 400, 500, 700 | [Google Fonts API](https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap) | SIL Open Font License 1.1, `../fonts/roboto/OFL.txt` |
| Material Icons | API revision v145; набор Material Icons | [Google Fonts API](https://fonts.googleapis.com/css?family=Material+Icons) | Apache License 2.0, `../fonts/material-icons/LICENSE` |

Roboto и Material Icons скачаны с официального домена `fonts.gstatic.com`
по адресам файлов, возвращённым Google Fonts API. Их локальные пути и
начертания указаны в `../css/fonts.css`.

Bootstrap source maps сохранены рядом с минифицированными CSS и JS. Для
корректного MIME `application/json` имена имеют окончание `.map.json`, а
ссылки `sourceMappingURL` в двух vendor-файлах указывают на эти имена.
Карты нужны только инструментам разработчика; загрузка самого интерфейса
от них не зависит.
