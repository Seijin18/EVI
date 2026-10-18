"""Combined sim fakes server (one Starlette app on 0.0.0.0:18080).

Routing:
* ``/bot<token>/<method>``        fake Telegram Bot API (``fake_telegram``)
* ``/api/...``                    fake Windmill (``fake_windmill``), which calls the
                                  SAME in-process ``FakeGoogle`` the runner seeds
* ``/message/..`` ``/chat/..``    fake Evolution API (``fake_evolution``); any other
                                  path -> 500 naming the URL (fail loudly)
* ``/health``                     liveness
* ``/_sim/...``                   runner controls (never used by the agent):
    POST /_sim/seed               google seed, or {"google": {...}, "evolution": {...}}
    POST /_sim/evolution/seed     contacts/chats/messages/profiles
    POST /_sim/evolution/state    {"state": "close"} changes the WhatsApp session state (default open)
    POST /_sim/evolution/message  one webhook-shaped message record appended to findMessages
    POST /_sim/telegram/updates   {"text", "chat_id"?} -> {"update_id"}
    GET  /_sim/telegram/sent      captured sendMessage calls
    POST /_sim/telegram/voice     {"audio_b64", "duration_s"?, "file_size"?, "chat_id"?} -> {"update_id"}
                                  (registers the audio for getFile/download + queues a voice update)
    POST /_sim/telegram/callback  {"message_id", "data", "chat_id"?, "from_id"?} -> {"update_id"} (a button tap)
    GET  /_sim/telegram/answers   captured answerCallbackQuery calls
    GET  /_sim/telegram/edits     captured editMessageReplyMarkup calls
    POST /_sim/telegram/faults    {"sendMessage": "transient", "count": N}
    GET  /_sim/evolution/sent     captured sendText calls (with recipient)
    POST /_sim/evolution/media    {"id", "audio_b64", "mimetype"?} registers media for getBase64FromMediaMessage
    POST|PUT|DELETE /_sim/faults, GET /_sim/calls   fake Windmill faults / call log
    GET  /_sim/state              {google, windmill_calls, telegram_sent, evolution_sent, media_requests}
    POST /_sim/reset              resets ALL fakes
"""

from __future__ import annotations

import base64

from testing.sim.fake_evolution import FakeEvolution
from testing.sim.fake_google import FakeGoogle
from testing.sim.fake_telegram import FakeTelegram
from testing.sim.fake_windmill import FakeWindmill
from testing.sim.fake_windmill import build_app as build_windmill_app

PORT = 18080


def build_app(
    google: FakeGoogle | None = None,
    windmill: FakeWindmill | None = None,
    telegram: FakeTelegram | None = None,
    evolution: FakeEvolution | None = None,
):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    g = google or FakeGoogle()
    w = windmill or FakeWindmill(g)
    t = telegram or FakeTelegram()
    e = evolution or FakeEvolution()
    all_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

    async def _json_body(req: Request) -> dict:
        try:
            data = await req.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    async def health(_req: Request):
        return JSONResponse({"ok": True})

    async def telegram_api(req: Request):
        if not t.check_token(req.path_params["token"]):
            return JSONResponse(
                {"ok": False, "error_code": 401, "description": "Unauthorized"}, status_code=401
            )
        params: dict = dict(req.query_params)
        if req.method == "POST":
            ctype = req.headers.get("content-type", "")
            if "json" in ctype:
                params.update(await _json_body(req))
            elif "form" in ctype:
                params.update({k: v for k, v in (await req.form()).items()})
        status, body = await t.call(req.path_params["method"], params)
        return JSONResponse(body, status_code=status)

    async def evolution_api(req: Request):
        body = await _json_body(req) if req.method == "POST" else None
        status, out = e.handle(req.method, req.url.path, dict(req.headers), body)
        return JSONResponse(out, status_code=status)

    async def seed(req: Request):
        data = await _json_body(req)
        if "google" in data or "evolution" in data:
            if "google" in data:
                g.seed(data["google"] or {})
            if "evolution" in data:
                e.seed(data["evolution"] or {})
        else:
            g.seed(data)
        return JSONResponse({"ok": True})

    async def evolution_seed(req: Request):
        e.seed(await _json_body(req))
        return JSONResponse({"ok": True})

    async def evolution_state(req: Request):
        e.set_state((await _json_body(req)).get("state"))
        return JSONResponse({"ok": True, "state": e.connection_state})

    async def evolution_message(req: Request):
        e.record_message(await _json_body(req))
        return JSONResponse({"ok": True})

    async def telegram_updates(req: Request):
        data = await _json_body(req)
        text = data.get("text")
        if not text:
            return JSONResponse({"error": "text required"}, status_code=400)
        uid = t.enqueue(text, data.get("chat_id"))
        return JSONResponse({"ok": True, "update_id": uid})

    async def telegram_callback(req: Request):
        data = await _json_body(req)
        if not data.get("data") or data.get("message_id") in (None, ""):
            return JSONResponse({"error": "message_id and data required"}, status_code=400)
        uid = t.enqueue_callback(data.get("chat_id"), data.get("from_id"), int(data["message_id"]), str(data["data"]))
        return JSONResponse({"ok": True, "update_id": uid})

    async def telegram_answers(_req: Request):
        return JSONResponse(t.answers)

    async def telegram_edits(_req: Request):
        return JSONResponse(t.edits)

    async def telegram_voice(req: Request):
        data = await _json_body(req)
        try:
            audio = base64.b64decode(data.get("audio_b64") or "", validate=True)
        except Exception:
            audio = b""
        if not audio:
            return JSONResponse({"error": "audio_b64 required"}, status_code=400)
        uid = t.enqueue_voice(
            audio,
            data.get("chat_id"),
            duration=int(data.get("duration_s") or 3),
            file_size=data.get("file_size"),
        )
        return JSONResponse({"ok": True, "update_id": uid})

    async def telegram_file(req: Request):
        if not t.check_token(req.path_params["token"]):
            return JSONResponse({"ok": False, "error_code": 401, "description": "Unauthorized"}, status_code=401)
        found = t.file_bytes(req.path_params["path"])
        if found is None:
            return JSONResponse({"ok": False, "error_code": 404, "description": "Not Found"}, status_code=404)
        return Response(found[0], media_type=found[1])

    async def evolution_media(req: Request):
        data = await _json_body(req)
        try:
            audio = base64.b64decode(data.get("audio_b64") or "", validate=True)
        except Exception:
            audio = b""
        if not data.get("id") or not audio:
            return JSONResponse({"error": "id and audio_b64 required"}, status_code=400)
        e.register_media(str(data["id"]), audio, data.get("mimetype") or "audio/ogg; codecs=opus")
        return JSONResponse({"ok": True})

    async def telegram_sent(_req: Request):
        return JSONResponse(t.sent)

    async def telegram_faults(req: Request):
        data = await _json_body(req)
        try:
            for method, kind in data.items():
                if method == "count":
                    continue
                t.set_fault(method, kind, count=int(data.get("count", 1)))
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "faults": t.state()["faults"]})

    async def evolution_sent(_req: Request):
        return JSONResponse(e.sent)

    async def state(_req: Request):
        return JSONResponse(
            {
                "google": g.state(),
                "windmill_calls": list(w.calls),
                "telegram_sent": list(t.sent),
                "evolution_sent": list(e.sent),
                "media_requests": list(e.media_requests),
            }
        )

    async def reset(_req: Request):
        g.reset()
        w.reset()
        t.reset()
        e.reset()
        return JSONResponse({"ok": True})

    wm_app = build_windmill_app(w)  # /api/... + /_sim/faults|calls (its own /_sim/reset is shadowed)

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/_sim/seed", seed, methods=["POST"]),
            Route("/_sim/state", state, methods=["GET"]),
            Route("/_sim/reset", reset, methods=["POST"]),
            Route("/_sim/evolution/seed", evolution_seed, methods=["POST"]),
            Route("/_sim/evolution/state", evolution_state, methods=["POST"]),
            Route("/_sim/evolution/message", evolution_message, methods=["POST"]),
            Route("/_sim/evolution/sent", evolution_sent, methods=["GET"]),
            Route("/_sim/telegram/updates", telegram_updates, methods=["POST"]),
            Route("/_sim/telegram/callback", telegram_callback, methods=["POST"]),
            Route("/_sim/telegram/answers", telegram_answers, methods=["GET"]),
            Route("/_sim/telegram/edits", telegram_edits, methods=["GET"]),
            Route("/_sim/telegram/voice", telegram_voice, methods=["POST"]),
            Route("/_sim/evolution/media", evolution_media, methods=["POST"]),
            Route("/_sim/telegram/sent", telegram_sent, methods=["GET"]),
            Route("/_sim/telegram/faults", telegram_faults, methods=["POST"]),
            Route("/_sim/faults", wm_app, methods=["POST", "PUT", "DELETE"]),
            Route("/_sim/calls", wm_app, methods=["GET"]),
            Route("/api/{path:path}", wm_app, methods=all_methods),
            Route("/file/bot{token}/{path:path}", telegram_file, methods=["GET"]),
            Route("/bot{token}/{method}", telegram_api, methods=["GET", "POST"]),
            Route("/{path:path}", evolution_api, methods=all_methods),
        ]
    )
    app.state.google = g
    app.state.windmill = w
    app.state.telegram = t
    app.state.evolution = e
    return app


app = build_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
