# Synthetic audio fixtures

Fictitious pt-BR speech used by the `SIM-VOICE-*` scenarios (`evi-voice-input`).
Nothing here is a real recording or real personal data.

| File | Spoken text |
|---|---|
| `marca_dentista.ogg` | "marca consulta no dentista amanhã às três da tarde" |
| `compromissos.ogg` | "quais meus compromissos de amanhã" |

Generated with eSpeak NG (`-v pt-br -s 120`) and encoded with `opusenc --bitrate 16`
(OGG/Opus, mono, under 15 KB each), inside a disposable Debian container (no TTS on the host):

```bash
docker run --rm -v "$PWD/tests/fixtures/audio:/out" debian:stable-slim sh -c \
  "apt-get update -qq && apt-get install -y -qq espeak-ng opus-tools >/dev/null && \
   espeak-ng -v pt-br -s 120 -w /tmp/a.wav 'marca consulta no dentista amanhã às três da tarde' && \
   opusenc --quiet --bitrate 16 /tmp/a.wav /out/marca_dentista.ogg && \
   espeak-ng -v pt-br -s 120 -w /tmp/b.wav 'quais meus compromissos de amanhã' && \
   opusenc --quiet --bitrate 16 /tmp/b.wav /out/compromissos.ogg"
```

Note: eSpeak pt-br mangles the bare phrase "marca dentista ..." (Gemini heard "Marca 20 ..."), so the
spoken text is "marca consulta no dentista ..." and speed is 120 wpm; the scenario expectations
(summary contains "dentista", start D1 15:00) are unchanged.
