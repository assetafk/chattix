# Chattix — real-time chat (Litestar)

WebSocket чат с комнатами, онлайн-статусом, Redis pub/sub и PostgreSQL.

## Запуск

Нужны **Python 3.11+**, запущенные **Docker** (PostgreSQL и Redis) или свои инстансы по URL из `.env`.

```bash
docker compose up -d
cp .env.example .env
python3.11 -m pip install -e .
uvicorn chattix.main:app --reload --host 0.0.0.0 --port 8000
```

Если Litestar падает с ошибкой импорта `MultipartSegment`, удалите пакет `python-multipart` (он конфликтует с зависимостью `multipart` у Litestar).

## API

- `POST /auth/register` — регистрация
- `POST /auth/login` — JWT
- `GET /rooms` — список комнат
- `POST /rooms` — создать комнату
- `POST /rooms/{id}/join` — вступить
- `GET /rooms/{id}/messages` — история (пагинация `limit`, `before_id`)
- `PATCH /messages/{id}` / `DELETE /messages/{id}` — редактирование / мягкое удаление
- `POST /messages/{id}/reactions` — реакция (`emoji`)
- `DELETE /messages/{id}/reactions/{emoji}`
- `POST /uploads` — загрузка файла (multipart), возвращает `url` для вставки в текст сообщения
- `GET /presence` — кто онлайн (из Redis)
- WebSocket: `/ws?token=<JWT>`

### Сообщения по WebSocket (JSON)

Клиент → сервер: `join_room`, `leave_room`, `send_message`, `typing`, `ping`.

Сервер → клиент: `message`, `message_edited`, `message_deleted`, `reaction_added`, `reaction_removed`, `typing`, `presence`, `pong`, `error`.
